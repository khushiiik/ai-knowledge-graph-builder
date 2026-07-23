import os
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Request, status, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from app.core.exceptions import (
    DocumentNotFoundException,
    FileStorageSaveException,
    IngestionQueueException,
    CredentialsValidationException,
    NoFilesProvidedException,
    AccessDeniedException,
    ExportFileNotFoundException,
)
from app.core.security import decode_access_token
from app.config import settings
from app.models.chunk import Chunk as ChunkModel
from app.db.neo4j_client import delete_document_facts
from app.pipeline.pipeline_runner import COLLECTION_NAME

from app.dependencies import get_db, get_current_active_user
from app.models.user import User as UserModel
from app.models.document import Document as DocumentModel, DocumentStatus
from app.schemas.document import DocumentRead
from app.utils.file_storage import save_upload_file, delete_stored_file
from app.validators.upload_validator import validate_uploaded_file

from app.models.processing_job import (
    ProcessingJob,
    ProcessingJobType,
    ProcessingJobStatus,
)
from app.workers.tasks import ingest_document_task

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload", response_model=List[DocumentRead], status_code=status.HTTP_201_CREATED
)
async def upload_document(
    request: Request,
    files: List[UploadFile] = File(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
) -> List[DocumentModel]:
    """Upload single or multiple files in a single request, validate them, and create document records."""
    files_to_upload: List[UploadFile] = []
    if files:
        for single_file in files:
            if single_file and single_file.filename:
                files_to_upload.append(single_file)
    if file and file.filename:
        files_to_upload.append(file)

    if not files_to_upload:
        raise NoFilesProvidedException()

    created_documents: List[DocumentModel] = []

    for upload_file in files_to_upload:
        validate_uploaded_file(upload_file, request)

        try:
            stored_filename, storage_path, file_size, checksum = save_upload_file(
                upload_file
            )
        except Exception as error:
            raise FileStorageSaveException(str(error))

        file_type = "unknown"
        if upload_file.filename and "." in upload_file.filename:
            file_type = upload_file.filename.split(".")[-1]

        mime_type = upload_file.content_type or "application/octet-stream"

        new_document = DocumentModel(
            user_id=current_user.id,
            original_filename=upload_file.filename or "unknown",
            stored_filename=stored_filename,
            storage_path=storage_path,
            file_type=file_type,
            mime_type=mime_type,
            file_size=file_size,
            checksum=checksum,
            status=DocumentStatus.QUEUED.value,
        )
        db.add(new_document)
        db.commit()
        db.refresh(new_document)

        processing_job = ProcessingJob(
            user_id=current_user.id,
            document_id=new_document.id,
            job_type=ProcessingJobType.DOCUMENT_INDEXING.value,
            status=ProcessingJobStatus.QUEUED.value,
        )
        db.add(processing_job)
        db.commit()
        db.refresh(processing_job)

        try:
            ingest_document_task.delay(
                job_id_str=str(processing_job.id),
                document_id_str=str(new_document.id),
                file_path=storage_path,
                mime_type=mime_type,
                tenant_id=current_user.id,
            )
        except Exception as error:
            new_document.status = DocumentStatus.FAILED.value
            processing_job.status = ProcessingJobStatus.FAILED.value
            processing_job.error_message = f"Failed to queue task: {str(error)}"
            db.commit()
            raise IngestionQueueException(str(error))

        created_documents.append(new_document)

    return created_documents


@router.get("", response_model=List[DocumentRead])
def list_documents(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """List all active (non-deleted) documents for the current active user."""
    active_documents = (
        db.query(DocumentModel)
        .filter(
            DocumentModel.user_id == current_user.id, DocumentModel.deleted_at.is_(None)
        )
        .all()
    )

    serialized_documents = []
    for document in active_documents:
        processing_job = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.document_id == document.id)
            .order_by(ProcessingJob.created_at.desc())
            .first()
        )

        job_progress = 0
        if processing_job:
            job_progress = processing_job.progress
        elif document.status == "READY":
            job_progress = 100

        serialized_documents.append(
            {
                "id": document.id,
                "user_id": document.user_id,
                "original_filename": document.original_filename,
                "stored_filename": document.stored_filename,
                "storage_path": document.storage_path,
                "file_type": document.file_type,
                "mime_type": document.mime_type,
                "file_size": document.file_size,
                "checksum": document.checksum,
                "status": document.status,
                "created_at": document.created_at,
                "updated_at": document.updated_at,
                "processed_at": document.processed_at,
                "deleted_at": document.deleted_at,
                "progress": job_progress,
                "current_step": processing_job.current_step if processing_job else None,
                "error_message": (
                    processing_job.error_message if processing_job else None
                ),
            }
        )
    return serialized_documents


@router.get("/{document_id}/status")
def get_document_status(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """Retrieve the status and processing state of a document."""
    document = (
        db.query(DocumentModel)
        .filter(
            DocumentModel.id == document_id, DocumentModel.user_id == current_user.id
        )
        .first()
    )
    if not document:
        raise DocumentNotFoundException()

    processing_job = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )

    job_progress = 0
    if processing_job:
        job_progress = processing_job.progress
    elif document.status == "READY":
        job_progress = 100

    return {
        "id": document.id,
        "status": document.status,
        "processed_at": document.processed_at,
        "deleted_at": document.deleted_at,
        "progress": job_progress,
        "current_step": processing_job.current_step if processing_job else None,
    }


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user),
):
    """Soft delete a document (updates status to DELETED and deletes chunks/facts from PostgreSQL, Qdrant, and Neo4j)."""
    document = (
        db.query(DocumentModel)
        .filter(
            DocumentModel.id == document_id,
            DocumentModel.user_id == current_user.id,
            DocumentModel.deleted_at.is_(None),
        )
        .first()
    )

    if not document:
        raise DocumentNotFoundException()

    delete_stored_file(document.storage_path)
    db.query(ChunkModel).filter(ChunkModel.document_id == document_id).delete()

    try:
        qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
        client = QdrantClient(url=qdrant_url)
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=qdrant_models.FilterSelector(
                filter=qdrant_models.Filter(
                    must=[
                        qdrant_models.FieldCondition(
                            key="metadata.source_file",
                            match=qdrant_models.MatchValue(
                                value=document.stored_filename
                            ),
                        ),
                        qdrant_models.FieldCondition(
                            key="metadata.tenant_id",
                            match=qdrant_models.MatchValue(value=current_user.id),
                        ),
                    ]
                )
            ),
        )
    except Exception as qdrant_error:
        print(f"Error deleting Qdrant vectors: {qdrant_error}")

    try:
        delete_document_facts(
            user_id=current_user.id, source_file=document.stored_filename
        )
    except Exception as neo4j_error:
        print(f"Error deleting Neo4j facts: {neo4j_error}")

    document.status = DocumentStatus.DELETED.value
    document.deleted_at = func.now()
    db.commit()

    return {
        "message": "Document and all matching vector/graph chunks deleted successfully"
    }


@router.get("/download/{filename}")
def download_export(filename: str, request: Request, db: Session = Depends(get_db)):
    """
    Serves a generated export file, enforcing strict user data isolation.
    Accepts authentication via Authorization header or ?token= query parameter.
    """
    access_token = None
    authorization_header = request.headers.get("Authorization")
    if authorization_header and authorization_header.startswith("Bearer "):
        access_token = authorization_header.split(" ")[1]
    if not access_token:
        access_token = request.query_params.get("token")

    if not access_token:
        raise CredentialsValidationException()

    decoded_payload = decode_access_token(access_token)
    if not decoded_payload:
        raise CredentialsValidationException()
    email = decoded_payload.get("sub")
    if not email:
        raise CredentialsValidationException()

    authenticated_user = db.query(UserModel).filter(UserModel.email == email).first()
    if not authenticated_user or not authenticated_user.is_active:
        raise CredentialsValidationException()

    file_path = os.path.join("storage", "exports", str(authenticated_user.id), filename)

    resolved_file_path = os.path.normpath(os.path.abspath(file_path))
    expected_directory_prefix = os.path.normpath(
        os.path.abspath(os.path.join("storage", "exports", str(authenticated_user.id)))
    )
    if not os.path.normcase(resolved_file_path).startswith(
        os.path.normcase(expected_directory_prefix)
    ):
        raise AccessDeniedException()

    if not os.path.exists(file_path):
        raise ExportFileNotFoundException()

    return FileResponse(file_path, filename=filename)
