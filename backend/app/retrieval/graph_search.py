from typing import Dict, List, Optional

from app.db.neo4j_client import query_related_facts
from app.pipeline.ner import extract_entities_and_relations


def graph_search(query: str, tenant_id: int, limit: int = 5, source_file: Optional[str] = None) -> List[Dict]:
    """
    Query Processing Flow, step 3 (Graph Search):
    1. Extract entity names mentioned in the user's question.
    2. Look up relationships involving those entities in this user's Neo4j graph.
    3. If source_file is provided, retrieve document-level relationships as fallback/additional context.
    4. Return them in the same {"text", "source"} shape as semantic chunks.
    """
    
    extraction = extract_entities_and_relations(query)
    entity_names = [e["name"] for e in extraction["entities"]]
    
    facts = []
    if entity_names:
        facts = query_related_facts(user_id=tenant_id, entity_names=entity_names, limit=limit)

    if source_file:
        from app.db.neo4j_client import query_document_facts
        doc_facts = query_document_facts(user_id=tenant_id, source_file=source_file, limit=limit)
        existing_keys = {(f["source"], f["relation"], f["target"]) for f in facts}
        for df in doc_facts:
            key = (df["source"], df["relation"], df["target"])
            if key not in existing_keys:
                facts.append(df)
                existing_keys.add(key)

    return [
        {
            "text": f"{fact['source']} {fact['relation']} {fact['target']}",
            "source": fact.get("source_doc") or "knowledge graph",
            "page": None,
            "type": "graph"
        }
        for fact in facts[:limit * 2]
    ]