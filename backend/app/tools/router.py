import logging
from typing import Dict, Any
import pandas as pd
from sqlalchemy.orm import Session

from app.api.services.document_service import load_csv
from app.models.document import Document as DocumentModel
from app.tools.chart_generator import ChartGenerator

logger = logging.getLogger(__name__)


class ToolRouter:

    @staticmethod
    def execute(
        tool_name: str, arguments: Dict[str, Any], db: Session, user_id: int
    ) -> Dict[str, Any]:
        """
        Routes the tool request to the appropriate tool execution logic.
        """
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

            from app.tools.spreadsheet_tool import execute_pandas_query
            result = execute_pandas_query(document.storage_path, plan)
            return {"result": result}

        elif tool_name == "chart_generator":
            document_id_str = arguments.get("document_id")
            chart_type = arguments.get("chart_type")
            x = arguments.get("x")
            y = arguments.get("y")
            aggregation = arguments.get("aggregation")

            if not document_id_str:
                raise ValueError("Missing document_id in arguments")
            if not chart_type:
                raise ValueError("Missing chart_type in arguments")
            if not x:
                raise ValueError("Missing x-axis column in arguments")

            # Fetch the document strictly enforcing data isolation
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

            # Load the CSV dataframe
            df = load_csv(document)

            # Match column names case-insensitively for user queries
            cols = {c.lower(): c for c in df.columns}
            x_col = cols.get(x.lower(), x)
            y_col = cols.get(y.lower(), y) if y else None

            # Handle server-side Pandas aggregations (sum, mean, avg, count, min, max)
            if aggregation and str(aggregation).lower() != "none":
                agg_type = aggregation.lower()
                if agg_type in ["sum", "mean", "avg", "count", "min", "max"]:
                    if agg_type == "avg":
                        agg_type = "mean"

                    if agg_type == "count":
                        if y_col:
                            df = (
                                df.groupby(x_col)[y_col]
                                .count()
                                .reset_index(name="count")
                            )
                        else:
                            df = (
                                df.groupby(x_col).size().reset_index(name="count")
                            )
                        y_col = "count"
                    else:
                        if y_col:
                            df[y_col] = pd.to_numeric(
                                df[y_col], errors="coerce"
                            )
                            df = (
                                df.groupby(x_col)[y_col]
                                .agg(agg_type)
                                .reset_index()
                            )
                        else:
                            raise ValueError(
                                f"Aggregation '{aggregation}' requires a numeric Y column"
                            )

            # Execute chart generation
            fig = ChartGenerator().generate(
                dataframe=df, chart_type=chart_type, x=x_col, y=y_col
            )
            import json
            return {"figure": json.loads(fig.to_json())}

        else:
            raise ValueError(f"Unknown tool: {tool_name}")
