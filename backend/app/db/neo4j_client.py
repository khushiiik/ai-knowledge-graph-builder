from typing import Dict, List

from neo4j import GraphDatabase

from app.config import settings

_driver = None


def get_neo4j_driver():
    """Lazily creates a single shared Neo4j driver instance for the app's lifetime."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
    return _driver


def write_graph_data(
    user_id: int,
    source_filename: str,
    entities: List[Dict],
    relationships: List[Dict],
) -> None:
    """
    Writes extracted entities/relationships into Neo4j, tagged with userId on every
    node and edge so graph queries can never cross tenants (mirrors the tenant_id
    filter used for Qdrant). Uses MERGE so re-processing a document or seeing the
    same entity again doesn't create duplicates.
    """
    if not entities and not relationships:
        return

    driver = get_neo4j_driver()
    with driver.session() as session:
        for entity in entities:
            session.run(
                """
                MERGE (e:Entity {name: $name, userId: $user_id})
                SET e.type = $type, e.lastSeenDocument = $source_filename
                """,
                name=entity["name"],
                type=entity.get("type", "UNKNOWN"),
                user_id=user_id,
                source_filename=source_filename,
            )

        for rel in relationships:
            session.run(
                """
                MERGE (a:Entity {name: $source, userId: $user_id})
                MERGE (b:Entity {name: $target, userId: $user_id})
                MERGE (a)-[r:RELATES_TO {type: $relation, userId: $user_id}]->(b)
                SET r.sourceDocument = $source_filename
                """,
                source=rel["source"],
                target=rel["target"],
                relation=rel.get("relation", "RELATED_TO"),
                user_id=user_id,
                source_filename=source_filename,
            )


def query_related_facts(user_id: int, entity_names: List[str], limit: int = 8) -> List[Dict]:
    """
    Given entity names mentioned in a user's question, finds relationships involving
    those entities in this user's graph (and only this user's graph, via userId).
    """
    if not entity_names:
        return []

    driver = get_neo4j_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Entity {userId: $user_id})-[r:RELATES_TO {userId: $user_id}]->(b:Entity {userId: $user_id})
            WHERE a.name IN $entity_names OR b.name IN $entity_names
            RETURN a.name AS source, r.type AS relation, b.name AS target, r.sourceDocument AS source_doc
            LIMIT $limit
            """,
            user_id=user_id,
            entity_names=entity_names,
            limit=limit,
        )
        return [dict(record) for record in result]


def query_all_user_facts(user_id: int, limit: int = 40) -> List[Dict]:
    """
    Retrieves all entity relationships for a user's knowledge graph.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Entity {userId: $user_id})-[r:RELATES_TO {userId: $user_id}]->(b:Entity {userId: $user_id})
            RETURN a.name AS source, r.type AS relation, b.name AS target, r.sourceDocument AS source_doc
            LIMIT $limit
            """,
            user_id=user_id,
            limit=limit,
        )
        return [dict(record) for record in result]


def query_document_facts(user_id: int, source_file: str, limit: int = 10) -> List[Dict]:
    """
    Retrieves relationships extracted from a specific document for a user.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Entity {userId: $user_id})-[r:RELATES_TO {userId: $user_id, sourceDocument: $source_file}]->(b:Entity {userId: $user_id})
            RETURN a.name AS source, r.type AS relation, b.name AS target, r.sourceDocument AS source_doc
            LIMIT $limit
            """,
            user_id=user_id,
            source_file=source_file,
            limit=limit,
        )
        return [dict(record) for record in result]


def delete_document_facts(user_id: int, source_file: str) -> None:
    """
    Deletes all relationships and orphaned entity nodes associated with a specific document.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        # Delete relationships
        session.run(
            """
            MATCH (a:Entity {userId: $user_id})-[r:RELATES_TO {userId: $user_id, sourceDocument: $source_file}]->(b:Entity {userId: $user_id})
            DELETE r
            """,
            user_id=user_id,
            source_file=source_file
        )
        # Delete orphaned nodes
        session.run(
            """
            MATCH (e:Entity {userId: $user_id})
            WHERE e.lastSeenDocument = $source_file AND NOT (e)-[:RELATES_TO]-()
            DELETE e
            """,
            user_id=user_id,
            source_file=source_file
        )