from typing import Dict, List, Optional

from app.db.neo4j_client import query_related_facts
from app.pipeline.ner import extract_entities_and_relations


def graph_search(query: str, tenant_id: int, limit: int = 5, source_file: Optional[str] = None) -> List[Dict]:
    """
    Query Processing Flow, step 3 (Graph Search):
    1. Extract entity names mentioned in the user's question.
    2. Look up relationships involving those entities in this user's Neo4j graph.
    3. If query is a broad schema/graph request or entity extraction is empty, fetch general graph facts.
    4. Return them in the same {"text", "source"} shape as semantic chunks.
    """
    is_schema_query = any(w in query.lower() for w in ('schema', 'graph', 'relational', 'map', 'relationship', 'all active', 'explore', 'tree'))

    extraction = extract_entities_and_relations(query)
    entity_names = [e["name"] for e in extraction["entities"]]
    
    facts = []
    if entity_names:
        facts = query_related_facts(user_id=tenant_id, entity_names=entity_names, limit=limit)

    if not facts or is_schema_query:
        from app.db.neo4j_client import query_all_user_facts
        all_facts = query_all_user_facts(user_id=tenant_id, limit=30)
        existing_keys = {(f["source"], f["relation"], f["target"]) for f in facts}
        for af in all_facts:
            key = (af["source"], af["relation"], af["target"])
            if key not in existing_keys:
                facts.append(af)
                existing_keys.add(key)

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