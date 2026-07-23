import pytest
import os
import shutil
from unittest.mock import patch, MagicMock
from app.tools.router import ToolRouter
from app.models.document import Document as DocumentModel


@pytest.fixture(autouse=True)
def clean_exports_dir():
    # Setup/Teardown storage/exports directory
    os.makedirs("storage/exports", exist_ok=True)
    yield
    if os.path.exists("storage/exports"):
        shutil.rmtree("storage/exports")


@patch("app.tools.router.get_llm_provider")
@patch("app.tools.router.retrieve_chunks")
@patch("app.tools.router.build_context_block")
def test_csv_export_generation(
    mock_context, mock_retrieve, mock_get_provider, db_session
):
    # Setup matching document
    doc = DocumentModel(
        user_id=1,
        original_filename="sample_export.pdf",
        stored_filename="stored_export.pdf",
        storage_path="/fake/path",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        checksum="checksum",
        status="READY",
    )
    db_session.add(doc)
    db_session.commit()

    # Mock LLM to return JSON records list
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content='[{"Name": "Alice", "Role": "Engineer"}, {"Name": "Bob", "Role": "Designer"}]'
    )

    mock_provider = MagicMock()
    mock_provider.llm = mock_llm
    mock_get_provider.return_value = mock_provider
    mock_context.return_value = "fake text content"

    result = ToolRouter.execute(
        tool_name="spreadsheet_export",
        arguments={
            "document_id": str(doc.id),
            "query": "list all roles",
            "format": "csv",
        },
        db=db_session,
        user_id=1,
    )

    assert "download_url" in result
    assert result["record_count"] == 2
    assert result["download_url"].endswith(".csv")


@patch("app.tools.router.get_llm_provider")
@patch("app.tools.router.retrieve_chunks")
@patch("app.tools.router.build_context_block")
def test_xlsx_export_generation(
    mock_context, mock_retrieve, mock_get_provider, db_session
):
    doc = DocumentModel(
        user_id=1,
        original_filename="sample_export.pdf",
        stored_filename="stored_export.pdf",
        storage_path="/fake/path",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        checksum="checksum",
        status="READY",
    )
    db_session.add(doc)
    db_session.commit()

    # Mock LLM
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(
        content='[{"Candidate": "John Doe", "Score": "95"}]'
    )

    mock_provider = MagicMock()
    mock_provider.llm = mock_llm
    mock_get_provider.return_value = mock_provider
    mock_context.return_value = "fake text content"

    result = ToolRouter.execute(
        tool_name="spreadsheet_export",
        arguments={
            "document_id": str(doc.id),
            "query": "list all candidate scores",
            "format": "excel",
        },
        db=db_session,
        user_id=1,
    )

    assert "download_url" in result
    assert result["record_count"] == 1
    assert result["download_url"].endswith(".xlsx")


@patch("app.tools.router.get_llm_provider")
@patch("app.tools.router.retrieve_chunks")
@patch("app.tools.router.build_context_block")
def test_empty_export_handled(
    mock_context, mock_retrieve, mock_get_provider, db_session
):
    doc = DocumentModel(
        user_id=1,
        original_filename="sample_export.pdf",
        stored_filename="stored_export.pdf",
        storage_path="/fake/path",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        checksum="checksum",
        status="READY",
    )
    db_session.add(doc)
    db_session.commit()

    # Mock LLM to return empty json list
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="[]")

    mock_provider = MagicMock()
    mock_provider.llm = mock_llm
    mock_get_provider.return_value = mock_provider
    mock_context.return_value = "fake text content"

    result = ToolRouter.execute(
        tool_name="spreadsheet_export",
        arguments={
            "document_id": str(doc.id),
            "query": "list nothing",
            "format": "csv",
        },
        db=db_session,
        user_id=1,
    )

    assert "download_url" in result
    assert result["record_count"] == 0
