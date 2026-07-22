import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.models.document import Document as DocumentModel
from app.db.neo4j_client import query_all_user_facts, query_document_facts

logger = logging.getLogger(__name__)

def execute_graph_extraction(
    db: Session,
    user_id: int,
    document_id_str: str | None,
    query: str
) -> Dict[str, Any]:
    """
    Retrieves nodes and edges from Neo4j to build a Cytoscape.js compatible graph:
    {
      "elements": [
        {"data": {"id": "node1", "label": "node1", "type": "Entity"}},
        {"data": {"id": "edge1", "source": "node1", "target": "node2", "label": "RELATION"}}
      ]
    }
    """
    logger.info(f"Starting graph retrieval for user {user_id}, query: {query}")

    # Fetch all user documents
    all_docs = db.query(DocumentModel).filter(
        DocumentModel.user_id == user_id,
        DocumentModel.deleted_at.is_(None)
    ).all()

    target_doc = None
    if all_docs:
        # Check if the query matches any document name (using normalized check)
        from app.tools.comparison_tool import normalize_name, clean_ext
        for doc in all_docs:
            doc_norm = normalize_name(clean_ext(doc.original_filename))
            query_norm = normalize_name(query)
            if doc_norm in query_norm or query_norm in doc_norm:
                target_doc = doc
                break

    # Focus fallback
    if not target_doc and document_id_str and document_id_str != "<document_id>":
        target_doc = (
            db.query(DocumentModel)
            .filter(
                DocumentModel.id == document_id_str,
                DocumentModel.user_id == user_id,
                DocumentModel.deleted_at.is_(None)
            )
            .first()
        )

    if target_doc:
        logger.info(f"Retrieving facts for specific document: {target_doc.original_filename}")
        facts = query_document_facts(user_id=user_id, source_file=target_doc.stored_filename, limit=100)
    else:
        logger.info("Retrieving all user facts")
        facts = query_all_user_facts(user_id=user_id, limit=100)

    # Convert Neo4j relationships to Cytoscape.js elements
    elements = []
    seen_nodes = set()

    for fact in facts:
        source = fact["source"]
        target = fact["target"]
        relation = fact["relation"]

        # Add source node
        if source not in seen_nodes:
            elements.append({
                "data": {
                    "id": source,
                    "label": source,
                    "type": "Entity"
                }
            })
            seen_nodes.add(source)

        # Add target node
        if target not in seen_nodes:
            elements.append({
                "data": {
                    "id": target,
                    "label": target,
                    "type": "Entity"
                }
            })
            seen_nodes.add(target)

        # Add relationship edge
        edge_id = f"{source}-{relation}-{target}"
        elements.append({
            "data": {
                "id": edge_id,
                "source": source,
                "target": target,
                "label": relation
            }
        })

    logger.info(f"Graph query returned {len(elements)} element(s) ({len(seen_nodes)} nodes).")
    return {"elements": elements}
