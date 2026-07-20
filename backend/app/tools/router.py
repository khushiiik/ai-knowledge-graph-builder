import json
import logging
import os
import re
import uuid
from typing import Dict, Any

import pandas as pd
from sqlalchemy.orm import Session

from app.api.services.document_service import load_csv
from app.llm.providers.factory import get_llm_provider
from app.models.document import Document as DocumentModel
from app.retrieval.semantic_search import retrieve_chunks, build_context_block
from app.tools.chart_generator import ChartGenerator
from app.tools.spreadsheet_tool import execute_pandas_query

logger = logging.getLogger(__name__)


class ToolRouter:

    @staticmethod
    def execute(
        tool_name: str, arguments: Dict[str, Any], db: Session, user_id: int
    ) -> Dict[str, Any]:
        """Routes tool request to appropriate execution logic."""
        logger.info(
            f"ToolRouter executing tool '{tool_name}' for user {user_id} with args: {arguments}"
        )

        if tool_name == "spreadsheet_query":
            document_id_str = arguments.get("document_id")
            plan = arguments.get("plan")
            if not document_id_str:
                raise ValueError("Missing document_id in arguments")
            if not plan:
                raise ValueError("Missing plan in arguments")

            document = (
                db.query(DocumentModel)
                .filter(
                    DocumentModel.id == document_id_str,
                    DocumentModel.user_id == user_id,
                )
                .first()
            )
            if not document:
                raise ValueError("Document not found or access denied")

            result = execute_pandas_query(document.storage_path, plan)
            return {"result": result}

        elif tool_name == "chart_generator":
            document_id_str = arguments.get("document_id")
            chart_type = arguments.get("chart_type", "bar")
            x = arguments.get("x")
            y = arguments.get("y")
            aggregation = arguments.get("aggregation")
            raw_data = arguments.get("data")

            # Document resolution with fallback
            document = None
            if document_id_str and document_id_str != "<document_id>":
                document = (
                    db.query(DocumentModel)
                    .filter(
                        DocumentModel.id == document_id_str,
                        DocumentModel.user_id == user_id,
                        DocumentModel.deleted_at.is_(None)
                    )
                    .first()
                )
            if not document:
                document = (
                    db.query(DocumentModel)
                    .filter(
                        DocumentModel.user_id == user_id,
                        DocumentModel.deleted_at.is_(None)
                    )
                    .order_by(DocumentModel.updated_at.desc())
                    .first()
                )

            df = None
            # Case 1: Inline extracted data array provided (from text/PDF/DOCX)
            if raw_data and isinstance(raw_data, list) and len(raw_data) > 0:
                df = pd.DataFrame(raw_data)
                cols = list(df.columns)
                x_col = x if (x and x in cols) else cols[0]
                y_col = y if (y and y in cols) else (cols[1] if len(cols) > 1 else None)
            # Case 2: Document is a spreadsheet CSV/Excel file
            elif document and document.file_type.lower() in ('csv', 'xlsx', 'xls'):
                df = load_csv(document)
                cols = {c.lower(): c for c in df.columns}
                x_col = cols.get(x.lower(), x) if x else df.columns[0]
                y_col = cols.get(y.lower(), y) if y else None

                # Handle server-side Pandas aggregations (sum, mean, avg, count, min, max)
                if aggregation and str(aggregation).lower() != "none":
                    agg_type = aggregation.lower()
                    if agg_type in ["sum", "mean", "avg", "count", "min", "max"]:
                        if agg_type == "avg":
                            agg_type = "mean"

                        if agg_type == "count":
                            if y_col:
                                df = df.groupby(x_col)[y_col].count().reset_index(name="count")
                            else:
                                df = df.groupby(x_col).size().reset_index(name="count")
                            y_col = "count"
                        else:
                            if y_col:
                                df[y_col] = pd.to_numeric(df[y_col], errors="coerce")
                                df = df.groupby(x_col)[y_col].agg(agg_type).reset_index()
                            else:
                                raise ValueError(f"Aggregation '{aggregation}' requires a numeric Y column")
            else:
                raise ValueError("No valid chart dataset or spreadsheet document found")

            if df is None or df.empty:
                raise ValueError("Chart dataset is empty")

            # Execute chart generation
            fig = ChartGenerator().generate(
                dataframe=df, chart_type=chart_type, x=x_col, y=y_col
            )
            return {"figure": json.loads(fig.to_json())}

        elif tool_name == "spreadsheet_export":
            document_id_str = arguments.get("document_id")
            query = arguments.get("query")
            export_format = arguments.get("format", "csv").lower()

            if not query:
                raise ValueError("Missing query in arguments")
            if export_format not in ("csv", "excel", "xlsx"):
                raise ValueError(f"Unsupported format: {export_format}")

            document = None
            if document_id_str and document_id_str != "<document_id>":
                document = (
                    db.query(DocumentModel)
                    .filter(
                        DocumentModel.id == document_id_str,
                        DocumentModel.user_id == user_id,
                        DocumentModel.deleted_at.is_(None)
                    )
                    .first()
                )

            # Fallback to the user's most recent non-deleted document if ID is missing or invalid
            if not document:
                document = (
                    db.query(DocumentModel)
                    .filter(
                        DocumentModel.user_id == user_id,
                        DocumentModel.deleted_at.is_(None)
                    )
                    .order_by(DocumentModel.updated_at.desc())
                    .first()
                )

            if not document:
                raise ValueError("No active document found for export")

            # Retrieve relevant chunks for context
            chunks = retrieve_chunks(query, tenant_id=user_id, limit=15, source_file=document.stored_filename)
            if not chunks:
                chunks = retrieve_chunks(query, tenant_id=user_id, limit=15)
            context_block = build_context_block(chunks)

            # Get LLM provider and extract structured records
            provider = get_llm_provider()

            extraction_prompt = [
                ("system", (
                    "You are an expert data analyst and data engineering agent.\n"
                    "Your task is to extract structured, high-quality tabular data from the provided document context based on the user's request: '{query}'.\n\n"
                    "FORMATTING & QUALITY RULES:\n"
                    "1. Thoroughly analyze the document context and identify all key entities, requirements, specifications, features, milestones, or key data points matching the request.\n"
                    "2. Create a logical, well-structured tabular schema with clear, informative column names.\n"
                    "   - For a requirements or project document, use columns such as: [\"ID\", \"Category / Section\", \"Item Name / Requirement\", \"Description / Details\", \"Priority / Status\", \"Tech Stack / Note\"].\n"
                    "   - For data sheets or candidate profiles, use relevant entity attributes as column headers.\n"
                    "3. Ensure EVERY object in the list uses the exact same keys (columns).\n"
                    "4. Values must be clear, complete, and informative text strings.\n"
                    "5. Output ONLY a valid JSON array of flat objects (key-value pairs). Do NOT include markdown code fences (```json), commentary, or explanations."
                ).format(query=query)),
                ("human", f"Document Context:\n{context_block}\n\nExtraction Request: {query}")
            ]

            response = provider.llm.invoke(extraction_prompt)
            response_content = str(response.content).strip()

            # Clean and parse response JSON robustly with fallback options
            records = None

            # 1. Try finding JSON array [...]
            array_match = re.search(r"\[[\s\S]*\]", response_content)
            if array_match:
                try:
                    records = json.loads(array_match.group(0))
                except Exception:
                    pass

            # 2. Try finding JSON object {...}
            if records is None:
                obj_match = re.search(r"\{[\s\S]*\}", response_content)
                if obj_match:
                    try:
                        parsed_obj = json.loads(obj_match.group(0))
                        if isinstance(parsed_obj, list):
                            records = parsed_obj
                        elif isinstance(parsed_obj, dict):
                            for k, v in parsed_obj.items():
                                if isinstance(v, list):
                                    records = v
                                    break
                            if records is None:
                                records = [parsed_obj]
                    except Exception:
                        pass

            # 3. Fallback: Parse markdown table or text lines if JSON parsing failed
            if records is None or not isinstance(records, list) or len(records) == 0:
                records = []
                lines = [l.strip() for l in response_content.splitlines() if l.strip()]
                table_lines = [l for l in lines if "|" in l]
                if len(table_lines) >= 2:
                    headers = [h.strip() for h in table_lines[0].split("|") if h.strip()]
                    for row_line in table_lines[1:]:
                        if "---" in row_line:
                            continue
                        cells = [c.strip() for c in row_line.split("|") if c.strip()]
                        if cells and len(cells) == len(headers):
                            records.append(dict(zip(headers, cells)))
                
                if not records:
                    for line in lines:
                        if line.startswith("```"):
                            continue
                        if ":" in line:
                            k, v = line.split(":", 1)
                            records.append({"Item": k.strip("-*# "), "Details": v.strip()})
                        elif len(line) > 3:
                            records.append({"Requirement / Information": line.strip("-*# ")})

            # Flatten any nested dictionaries in values to strings for clean Pandas CSV export
            if records:
                flat_records = []
                for rec in records:
                    if isinstance(rec, dict):
                        flat_rec = {}
                        for k, v in rec.items():
                            if isinstance(v, (dict, list)):
                                flat_rec[k] = json.dumps(v)
                            else:
                                flat_rec[k] = v
                        flat_records.append(flat_rec)
                records = flat_records

            # Convert to Pandas DataFrame
            if not records:
                df = pd.DataFrame(columns=["No records found"])
            else:
                df = pd.DataFrame(records)

            # Create user-specific exports directory to enforce strict data isolation
            export_dir = os.path.join("storage", "exports", str(user_id))
            os.makedirs(export_dir, exist_ok=True)

            ext = "xlsx" if export_format in ("excel", "xlsx") else "csv"
            export_filename = f"{uuid.uuid4()}.{ext}"
            file_path = os.path.join(export_dir, export_filename)

            if ext == "xlsx":
                df.to_excel(file_path, index=False)
            else:
                df.to_csv(file_path, index=False)

            return {
                "download_url": f"/documents/download/{export_filename}",
                "filename": export_filename,
                "record_count": len(df) if records else 0
            }

        else:
            raise ValueError(f"Unknown tool: {tool_name}")
