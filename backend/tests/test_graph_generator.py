import pytest
from unittest.mock import patch
from app.tools.graph_tool import execute_graph_extraction


@patch("app.tools.graph_tool.query_all_user_facts")
def test_empty_graph_handled(mock_query, db_session):
    mock_query.return_value = []

    result = execute_graph_extraction(
        db=db_session, user_id=1, document_id_str=None, query="show me the graph"
    )
    assert "elements" in result
    assert len(result["elements"]) == 0


@patch("app.tools.graph_tool.query_all_user_facts")
def test_graph_elements_nodes_and_edges(mock_query, db_session):
    # Mock Neo4j query response
    mock_query.return_value = [
        {"source": "Alice", "target": "Bob", "relation": "FRIEND_OF"}
    ]

    result = execute_graph_extraction(
        db=db_session, user_id=1, document_id_str=None, query="show me the graph"
    )

    assert "elements" in result
    elements = result["elements"]

    # We expect 2 nodes ("Alice", "Bob") and 1 edge
    assert len(elements) == 3

    nodes = [e for e in elements if e["data"].get("type") == "Entity"]
    edges = [e for e in elements if "source" in e["data"]]

    assert len(nodes) == 2
    assert len(edges) == 1

    node_ids = {n["data"]["id"] for n in nodes}
    assert "Alice" in node_ids
    assert "Bob" in node_ids

    assert edges[0]["data"]["source"] == "Alice"
    assert edges[0]["data"]["target"] == "Bob"
    assert edges[0]["data"]["label"] == "FRIEND_OF"


@patch("app.tools.graph_tool.query_document_facts")
@patch("app.tools.graph_tool.clean_ext")
@patch("app.tools.graph_tool.normalize_name")
def test_graph_scoped_to_document(mock_norm, mock_clean, mock_query, db_session):
    from app.models.document import Document as DocumentModel

    # Add a document to check matching doc name branch
    doc = DocumentModel(
        user_id=1,
        original_filename="Sample_File.pdf",
        stored_filename="sample_stored.pdf",
        storage_path="/fake/path",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        checksum="abc",
        status="READY",
    )
    db_session.add(doc)
    db_session.commit()

    mock_clean.return_value = "sample file"
    mock_norm.return_value = "sample file"
    mock_query.return_value = [{"source": "X", "target": "Y", "relation": "CONNECTS"}]

    result = execute_graph_extraction(
        db=db_session,
        user_id=1,
        document_id_str=str(doc.id),
        query="show graph for Sample_File",
    )

    # Verification
    mock_query.assert_called_once_with(
        user_id=1, source_file="sample_stored.pdf", limit=100
    )
    assert len(result["elements"]) == 3
