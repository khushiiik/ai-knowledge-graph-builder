import pytest
from unittest.mock import patch, MagicMock
from app.tools.comparison_tool import (
    execute_comparison_extraction,
    clean_ext,
    normalize_name,
)
from app.models.document import Document as DocumentModel


def test_clean_ext_utility():
    assert clean_ext("report.pdf") == "report"
    assert clean_ext("data.xlsx") == "data"
    assert clean_ext("unknown.ext") == "unknown.ext"


def test_normalize_name_utility():
    assert normalize_name("Solaris_Byte_Systems_Data") == "solaris byte systems data"
    assert normalize_name("IT-Company-Report") == "it company report"


@patch("app.tools.comparison_tool.get_llm_provider")
def test_comparison_with_no_documents(mock_get_provider, db_session):
    result = execute_comparison_extraction(
        db_session, user_id=1, document_id_str=None, query="compare A and B"
    )
    assert "warning" in result
    assert "empty" in result["warning"]


@patch("app.tools.comparison_tool.get_llm_provider")
@patch("app.tools.comparison_tool.retrieve_chunks")
def test_comparison_with_missing_document_warnings(
    mock_retrieve, mock_get_provider, db_session
):
    # Setup single document
    doc = DocumentModel(
        user_id=1,
        original_filename="Solaris_Byte_Systems_Data_Report.pdf",
        stored_filename="solaris_stored.pdf",
        storage_path="/fake/path",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        checksum="abc",
        status="READY",
    )
    db_session.add(doc)
    db_session.commit()

    # Mock LLM to return list including a missing document ("IT Company Data")
    mock_llm = MagicMock()
    # First invoke returns compared entities list, second invoke returns matrix
    mock_llm.invoke.return_value = MagicMock(
        content='["Solaris Byte Systems Data", "IT Company Data"]'
    )

    mock_provider = MagicMock()
    mock_provider.llm = mock_llm
    mock_get_provider.return_value = mock_provider

    result = execute_comparison_extraction(
        db_session,
        user_id=1,
        document_id_str=None,
        query="compare Solaris Byte Systems Data and IT Company Data",
    )
    assert "warning" in result
    assert "IT Company Data" in result["warning"]
    assert "not available" in result["warning"]


@patch("app.tools.comparison_tool.get_llm_provider")
@patch("app.tools.comparison_tool.retrieve_chunks")
@patch("app.tools.comparison_tool.build_context_block")
def test_comparison_successful_matrix(
    mock_context, mock_retrieve, mock_get_provider, db_session
):
    # Setup matching documents
    doc1 = DocumentModel(
        user_id=1,
        original_filename="Solaris_Report.pdf",
        stored_filename="solaris_stored.pdf",
        storage_path="/fake/path",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        checksum="abc",
        status="READY",
    )
    doc2 = DocumentModel(
        user_id=1,
        original_filename="IT_Report.pdf",
        stored_filename="it_stored.pdf",
        storage_path="/fake/path2",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        checksum="def",
        status="READY",
    )
    db_session.add_all([doc1, doc2])
    db_session.commit()

    # Mock LLM calls
    mock_llm = MagicMock()
    # First returns names matching our docs
    response1 = MagicMock(content='["Solaris Report", "IT Report"]')
    # Second returns valid comparison matrix JSON structure
    response2 = MagicMock(
        content='{"headers": ["Feature / Attribute", "Solaris Report", "IT Report"], "rows": [{"Feature / Attribute": "Employees", "Solaris Report": "100", "IT Report": "200"}]}'
    )
    mock_llm.invoke.side_effect = [response1, response2]

    mock_provider = MagicMock()
    mock_provider.llm = mock_llm
    mock_get_provider.return_value = mock_provider
    mock_context.return_value = "fake text context"

    result = execute_comparison_extraction(
        db_session,
        user_id=1,
        document_id_str=None,
        query="compare Solaris Report and IT Report",
    )
    assert "headers" in result
    assert "rows" in result
    assert "Solaris Report" in result["headers"]
    assert len(result["rows"]) == 1
    assert result["rows"][0]["Feature / Attribute"] == "Employees"
