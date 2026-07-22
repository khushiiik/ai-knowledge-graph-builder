import re
import json
import logging
import difflib
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.document import Document as DocumentModel
from app.retrieval.semantic_search import retrieve_chunks, build_context_block
from app.llm.providers.factory import get_llm_provider

logger = logging.getLogger(__name__)

def clean_ext(filename: str) -> str:
    orig_clean = filename.lower()
    for ext in ['.docx', '.pdf', '.csv', '.xlsx', '.txt']:
        if orig_clean.endswith(ext):
            return filename[:-len(ext)]
    return filename

def normalize_name(name: str) -> str:
    n = name.lower()
    n = n.replace('_', ' ').replace('-', ' ')
    return " ".join(n.split())

def find_document_match(extracted_name: str, all_docs: List[DocumentModel]):
    extracted_norm = normalize_name(extracted_name)
    if not extracted_norm:
        return None, None
    
    # 1. Check for exact or substring match after normalization
    for doc in all_docs:
        orig_clean = clean_ext(doc.original_filename)
        orig_norm = normalize_name(orig_clean)
        if extracted_norm == orig_norm or extracted_norm in orig_norm or orig_norm in extracted_norm:
            return doc, None
            
    # 2. Check for close fuzzy match using normalized names
    doc_names_map = {}
    for doc in all_docs:
        orig_clean = clean_ext(doc.original_filename)
        orig_norm = normalize_name(orig_clean)
        doc_names_map[orig_norm] = doc
        
    matches = difflib.get_close_matches(extracted_norm, list(doc_names_map.keys()), n=1, cutoff=0.5)
    if matches:
        closest_norm = matches[0]
        return None, clean_ext(doc_names_map[closest_norm].original_filename)
        
    return None, None

def execute_comparison_extraction(
    db: Session,
    user_id: int,
    document_id_str: str | None,
    query: str
) -> Dict[str, Any]:
    """
    Compares entities across documents and extracts a structured comparison matrix.
    Checks document availability and suggests correction if a name is misspelled.
    """
    logger.info(f"Starting comparison extraction for user {user_id}, query: {query}")

    # Fetch all user documents
    all_docs = db.query(DocumentModel).filter(
        DocumentModel.user_id == user_id,
        DocumentModel.deleted_at.is_(None)
    ).all()

    if len(all_docs) == 0:
        return {"warning": "Your knowledge base is empty. Please upload documents before generating a comparison."}

    # Query LLM to extract entity/document names from user query
    provider = get_llm_provider()
    doc_list_prompt = [
        ("system", (
            "You are an assistant that extracts entity or document names from user comparison queries.\n"
            "Based on the user query, identify the names of the documents, companies, projects, or entities the user wants to compare.\n"
            "Return ONLY a JSON list of strings, for example: [\"Solaris Byte Systems Data\", \"IT Company Data\"].\n"
            "Do not return any other text, markdown, or comments."
        )),
        ("human", f"User query: {query}")
    ]

    extracted_names = []
    try:
        extract_resp = provider.llm.invoke(doc_list_prompt)
        match = re.search(r"\[[\s\S]*\]", str(extract_resp.content))
        if match:
            extracted_names = json.loads(match.group(0))
    except Exception as e:
        logger.error(f"Failed to extract document names from query: {e}")

    # Validate extracted entities against uploaded documents
    if extracted_names:
        for name in extracted_names:
            doc, suggestion = find_document_match(name, all_docs)
            if not doc:
                if suggestion:
                    return {"warning": f'"{name}" is not available. Did you mean "{suggestion}"?'}
                else:
                    return {"warning": f'"{name}" is not available in your knowledge base. Please upload it to compare.'}

    # For comparison, we retrieve chunks across all documents (source_file = None)
    search_query = f"{query} compare comparison difference side-by-side details features specifications candidate product company project candidates products companies projects"
    chunks = retrieve_chunks(search_query, tenant_id=user_id, limit=25, source_file=None)

    context_block = build_context_block(chunks)
    if not context_block:
        logger.warning(f"No comparison context retrieved for query: {query}")
        return {"headers": ["Feature / Attribute"], "rows": []}

    # Query LLM to extract comparison matrix
    system_prompt = (
        "You are an expert data synthesis and business intelligence assistant.\n"
        f"Your task is to analyze the provided document context and generate a side-by-side comparison matrix for the entities mentioned in the query: '{query}'.\n\n"
        "STEPS:\n"
        "1. Identify the key entities being compared (e.g. Project A and Project B, candidate John and candidate Jane, product X and product Y).\n"
        "2. Identify the key attributes, features, metrics, or specifications for comparison (e.g. Cost, Status, Timeline, Experience, Features, Pros, Cons).\n"
        "3. Generate a structured JSON response with the following keys:\n"
        "   - 'headers': An array of strings where the first element is 'Feature / Attribute', followed by the names of the entities compared.\n"
        "   - 'rows': An array of flat objects where each object represents a feature row. The keys of the objects must exactly match the values in the 'headers' array. For example, if headers are ['Feature / Attribute', 'Entity A', 'Entity B'], each row must look like: { 'Feature / Attribute': 'Cost', 'Entity A': '$10k', 'Entity B': '$15k' }.\n\n"
        "Output ONLY a valid JSON object of the format: { \"headers\": [...], \"rows\": [...] }. Do not include markdown code fences, comments, or explanations."
    )
    extraction_prompt = [
        ("system", system_prompt),
        ("human", f"Document Context:\n{context_block}\n\nComparison Request: {query}")
    ]

    response = provider.llm.invoke(extraction_prompt)
    response_content = str(response.content).strip()

    result = {"headers": ["Feature / Attribute"], "rows": []}
    # Attempt to locate and parse JSON object {...}
    obj_match = re.search(r"\{[\s\S]*\}", response_content)
    if obj_match:
        try:
            parsed = json.loads(obj_match.group(0))
            if isinstance(parsed, dict) and "headers" in parsed and "rows" in parsed:
                # Basic validation
                headers = [str(h).strip() for h in parsed["headers"] if h]
                rows = []
                for r in parsed["rows"]:
                    if isinstance(r, dict):
                        row_obj = {}
                        for h in headers:
                            row_obj[h] = str(r.get(h, r.get(h.lower(), "N/A"))).strip()
                        rows.append(row_obj)
                if len(headers) > 1:
                    result = {"headers": headers, "rows": rows}
        except Exception as e:
            logger.error(f"Failed to parse comparison JSON object: {e}")

    logger.info(f"Successfully generated comparison table with {len(result['rows'])} rows.")
    return result
