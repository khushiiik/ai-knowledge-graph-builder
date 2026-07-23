from typing import Dict, List, Optional

from app.db.neo4j_client import query_related_facts
from app.pipeline.ner import extract_entities_and_relations


def graph_search(
    query: str, tenant_id: int, limit: int = 5, source_file: Optional[str] = None
) -> List[Dict]:
    """
    Query Processing Flow, step 3 (Graph Search):
    1. Extract entity names mentioned in the user's question.
    2. Look up relationships involving those entities in this user's Neo4j graph.
    3. If query is a broad schema/graph request or entity extraction is empty, fetch general graph facts.
    4. Return them in the same {"text", "source"} shape as semantic chunks.
    """
    query_lower = query.lower()
    schema_keywords = (
        "schema",
        "graph",
        "relational",
        "map",
        "relationship",
        "all active",
        "explore",
        "tree",
    )

    is_schema_query = False
    for keyword in schema_keywords:
        if keyword in query_lower:
            is_schema_query = True
            break

    extracted_entities_payload = extract_entities_and_relations(query)

    entity_names = []
    for entity in extracted_entities_payload["entities"]:
        entity_names.append(entity["name"])

    facts = []
    if entity_names:
        facts = query_related_facts(
            user_id=tenant_id, entity_names=entity_names, limit=limit
        )

    if not facts or is_schema_query:
        from app.db.neo4j_client import query_all_user_facts

        all_user_facts = query_all_user_facts(user_id=tenant_id, limit=30)
        existing_keys = set()
        for fact in facts:
            existing_keys.add((fact["source"], fact["relation"], fact["target"]))

        for user_fact in all_user_facts:
            key = (user_fact["source"], user_fact["relation"], user_fact["target"])
            if key not in existing_keys:
                facts.append(user_fact)
                existing_keys.add(key)

    if source_file:
        from app.db.neo4j_client import query_document_facts

        document_facts = query_document_facts(
            user_id=tenant_id, source_file=source_file, limit=limit
        )
        existing_keys = set()
        for fact in facts:
            existing_keys.add((fact["source"], fact["relation"], fact["target"]))

        for document_fact in document_facts:
            key = (
                document_fact["source"],
                document_fact["relation"],
                document_fact["target"],
            )
            if key not in existing_keys:
                facts.append(document_fact)
                existing_keys.add(key)

    formatted_facts = []
    for fact in facts[: limit * 2]:
        formatted_facts.append(
            {
                "text": f"{fact['source']} {fact['relation']} {fact['target']}",
                "source": fact.get("source_doc") or "knowledge graph",
                "page": None,
                "type": "graph",
            }
        )
    return formatted_facts
