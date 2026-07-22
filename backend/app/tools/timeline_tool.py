import re
import json
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models.document import Document as DocumentModel
from app.retrieval.semantic_search import retrieve_chunks, build_context_block
from app.llm.providers.factory import get_llm_provider

logger = logging.getLogger(__name__)

def execute_timeline_extraction(
    db: Session,
    user_id: int,
    document_id_str: str | None,
    query: str
) -> List[Dict[str, str]]:
    """
    Extracts dated events from a document's semantic chunks and parses them into a
    structured JSON array: [{"date": "...", "title": "...", "description": "..."}]
    """
    logger.info(f"Starting timeline extraction for user {user_id}, doc: {document_id_str}, query: {query}")
    
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
        logger.warning(f"No document found for timeline extraction for user {user_id}")
        return []

    # Retrieve relevant chunks from the vector database
    search_query = f"{query} timeline history dates events milestones chronological"
    chunks = retrieve_chunks(search_query, tenant_id=user_id, limit=25, source_file=document.stored_filename)
    if not chunks:
        chunks = retrieve_chunks(search_query, tenant_id=user_id, limit=25)

    context_block = build_context_block(chunks)
    if not context_block:
        logger.warning(f"No text content could be retrieved for document {document.id}")
        return []

    # Get LLM provider and call it to extract timeline events
    provider = get_llm_provider()
    extraction_prompt = [
        ("system", (
            "You are an expert timeline builder and data extraction assistant.\n"
            "Thoroughly analyze the provided context and extract all key historical events, milestones, occurrences, and changes chronologically.\n\n"
            "For each event, extract the following information:\n"
            "1. 'date': The exact date, timestamp, or time frame mentioned (e.g. '2024-05-12', 'Q3 2023', 'June 15, 2021', 'October 1999'). Do not use relative terms like 'today' or 'last year'.\n"
            "2. 'title': A short, clear name/label summarizing the event (e.g. 'Company Founded', 'Product Beta Release').\n"
            "3. 'description': A concise sentence describing what happened.\n"
            "4. 'group': A short string category for the event to group similar activities (e.g. 'Engineering', 'Marketing', 'Legal', 'Sales', 'Milestones', 'Operations'). Keep this string very short (1-2 words) and consistent across events.\n\n"
            "Output ONLY a valid JSON array of objects containing 'date', 'title', 'description', and 'group' fields. Do not include markdown code blocks (such as ```json), explanations, or commentary."
        )),
        ("human", f"Document Context:\n{context_block}\n\nTimeline Request: {query}")
    ]

    response = provider.llm.invoke(extraction_prompt)
    response_content = str(response.content).strip()

    events = []
    # Attempt to locate and parse JSON array [...]
    array_match = re.search(r"\[[\s\S]*\]", response_content)
    if array_match:
        try:
            events = json.loads(array_match.group(0))
        except Exception as e:
            logger.error(f"Failed to parse JSON array from model response: {e}")

    # Standardize output keys
    parsed_events = []
    if isinstance(events, list):
        for item in events:
            if isinstance(item, dict):
                date_val = item.get("date", item.get("time", ""))
                title_val = item.get("title", item.get("event", ""))
                desc_val = item.get("description", item.get("details", ""))
                group_val = item.get("group", item.get("category", "General"))
                
                # Check that we have at least date and title
                if date_val and title_val:
                    parsed_events.append({
                        "date": str(date_val).strip(),
                        "title": str(title_val).strip(),
                        "description": str(desc_val).strip(),
                        "group": str(group_val).strip() if group_val else "General"
                    })

    logger.info(f"Successfully extracted {len(parsed_events)} events from timeline tool.")
    return parsed_events
