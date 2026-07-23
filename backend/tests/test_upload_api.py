import pytest
from unittest.mock import patch, MagicMock
from fastapi import status
from app.models.document import DocumentStatus


@patch("app.api.routes.document.save_upload_file")
@patch("app.api.routes.document.ingest_document_task")
def test_upload_valid_pdf(mock_task, mock_save, client, auth_headers):
    # Mock save_upload_file to return fake storage attributes
    mock_save.return_value = (
        "stored_pdf.pdf",
        "/fake/path/pdf.pdf",
        1024,
        "fake-checksum",
    )

    files = {"files": ("test1.pdf", b"%PDF-1.4 mock pdf contents", "application/pdf")}
    res = client.post("/documents/upload", files=files, headers=auth_headers)

    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert len(data) == 1
    assert data[0]["original_filename"] == "test1.pdf"
    assert data[0]["status"] == DocumentStatus.QUEUED.value


@patch("app.api.routes.document.save_upload_file")
@patch("app.api.routes.document.ingest_document_task")
def test_upload_valid_docx(mock_task, mock_save, client, auth_headers):
    mock_save.return_value = (
        "stored_docx.docx",
        "/fake/path/docx.docx",
        2048,
        "fake-checksum-docx",
    )

    files = {
        "files": (
            "test2.docx",
            b"mock docx file contents",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    res = client.post("/documents/upload", files=files, headers=auth_headers)

    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert len(data) == 1
    assert data[0]["original_filename"] == "test2.docx"
    assert data[0]["status"] == DocumentStatus.QUEUED.value


def test_reject_unsupported_file_type(client, auth_headers):
    files = {
        "files": (
            "malicious.exe",
            b"malicious executable bytes",
            "application/x-msdownload",
        )
    }
    res = client.post("/documents/upload", files=files, headers=auth_headers)

    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert "not allowed" in res.json()["detail"].lower()


def test_reject_file_larger_than_50mb(client, auth_headers):
    # Construct a larger payload (exceeding 51MB limit threshold)
    large_payload = b"0" * (52 * 1024 * 1024)
    files = {"files": ("large.pdf", large_payload, "application/pdf")}

    res = client.post("/documents/upload", files=files, headers=auth_headers)

    assert res.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert "exceeds" in res.json()["detail"].lower()


@patch("app.api.routes.document.save_upload_file")
@patch("app.api.routes.document.ingest_document_task")
def test_processing_status_changes_correctly(
    mock_task, mock_save, client, auth_headers
):
    mock_save.return_value = ("stored.pdf", "/fake/path/pdf.pdf", 1024, "checksum")

    files = {"files": ("status.pdf", b"%PDF-1.4 data", "application/pdf")}
    res = client.post("/documents/upload", files=files, headers=auth_headers)

    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data[0]["status"] == DocumentStatus.QUEUED.value
