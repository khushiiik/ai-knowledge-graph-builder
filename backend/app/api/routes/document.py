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
    CredentialsValidationException
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

from app.models.processing_job import ProcessingJob, ProcessingJobType, ProcessingJobStatus
from app.workers.tasks import ingest_document_task

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=List[DocumentRead], status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    files: List[UploadFile] = File(None),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
) -> List[DocumentModel]:
    """Upload single or multiple files in a single request, validate them, and create document records."""
    upload_list: List[UploadFile] = []
    if files:
        upload_list.extend([f for f in files if f and f.filename])
    if file and file.filename:
        upload_list.append(file)

    if not upload_list:
        raise HTTPException(status_code=400, detail="No valid file(s) provided in upload request.")

    created_documents: List[DocumentModel] = []

    for upload_file in upload_list:
        validate_uploaded_file(upload_file, request)

        try:
            stored_filename, storage_path, file_size, checksum = save_upload_file(upload_file)
        except Exception as e:
            raise FileStorageSaveException(str(e))

        file_type = upload_file.filename.split(".")[-1] if upload_file.filename and "." in upload_file.filename else "unknown"
        mime_type = upload_file.content_type or "application/octet-stream"

        new_doc = DocumentModel(
            user_id=current_user.id,
            original_filename=upload_file.filename or "unknown",
            stored_filename=stored_filename,
            storage_path=storage_path,
            file_type=file_type,
            mime_type=mime_type,
            file_size=file_size,
            checksum=checksum,
            status=DocumentStatus.QUEUED.value
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        job = ProcessingJob(
            user_id=current_user.id,
            document_id=new_doc.id,
            job_type=ProcessingJobType.DOCUMENT_INDEXING.value,
            status=ProcessingJobStatus.QUEUED.value
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        try:
            ingest_document_task.delay(
                job_id_str=str(job.id),
                document_id_str=str(new_doc.id),
                file_path=storage_path,
                mime_type=mime_type,
                tenant_id=current_user.id
            )
        except Exception as e:
            new_doc.status = DocumentStatus.FAILED.value
            job.status = ProcessingJobStatus.FAILED.value
            job.error_message = f"Failed to queue task: {str(e)}"
            db.commit()
            raise IngestionQueueException(str(e))

        created_documents.append(new_doc)

    return created_documents


@router.get("", response_model=List[DocumentRead])
def list_documents(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """List all active (non-deleted) documents for the current active user."""
    docs = db.query(DocumentModel).filter(
        DocumentModel.user_id == current_user.id,
        DocumentModel.deleted_at.is_(None)
    ).all()

    read_docs = []
    for doc in docs:
        job = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.document_id == doc.id)
            .order_by(ProcessingJob.created_at.desc())
            .first()
        )
        read_docs.append({
            "id": doc.id,
            "user_id": doc.user_id,
            "original_filename": doc.original_filename,
            "stored_filename": doc.stored_filename,
            "storage_path": doc.storage_path,
            "file_type": doc.file_type,
            "mime_type": doc.mime_type,
            "file_size": doc.file_size,
            "checksum": doc.checksum,
            "status": doc.status,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
            "processed_at": doc.processed_at,
            "deleted_at": doc.deleted_at,
            "progress": job.progress if job else (100 if doc.status == "READY" else 0),
            "current_step": job.current_step if job else None,
            "error_message": job.error_message if job else None
        })
    return read_docs

@router.get("/{document_id}/status")
def get_document_status(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Retrieve the status and processing state of a document."""
    doc = db.query(DocumentModel).filter(
        DocumentModel.id == document_id,
        DocumentModel.user_id == current_user.id
    ).first()
    if not doc:
        raise DocumentNotFoundException()
    
    job = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.created_at.desc())
        .first()
    )

    return {
        "id": doc.id,
        "status": doc.status,
        "processed_at": doc.processed_at,
        "deleted_at": doc.deleted_at,
        "progress": job.progress if job else (100 if doc.status == "READY" else 0),
        "current_step": job.current_step if job else None
    }

@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Soft delete a document (updates status to DELETED and deletes chunks/facts from PostgreSQL, Qdrant, and Neo4j)."""
    doc = db.query(DocumentModel).filter(
        DocumentModel.id == document_id,
        DocumentModel.user_id == current_user.id,
        DocumentModel.deleted_at.is_(None)
    ).first()
    
    if not doc:
        raise DocumentNotFoundException()

    delete_stored_file(doc.storage_path)
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
                            match=qdrant_models.MatchValue(value=doc.stored_filename)
                        ),
                        qdrant_models.FieldCondition(
                            key="metadata.tenant_id",
                            match=qdrant_models.MatchValue(value=current_user.id)
                        )
                    ]
                )
            )
        )
    except Exception as qe:
        print(f"Error deleting Qdrant vectors: {qe}")

    try:
        delete_document_facts(user_id=current_user.id, source_file=doc.stored_filename)
    except Exception as ne:
        print(f"Error deleting Neo4j facts: {ne}")

    doc.status = DocumentStatus.DELETED.value
    doc.deleted_at = func.now()
    db.commit()

    return {"message": "Document and all matching vector/graph chunks deleted successfully"}


@router.get("/download/{filename}")
def download_export(
    filename: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Serves a generated export file, enforcing strict user data isolation.
    Accepts authentication via Authorization header or ?token= query parameter.
    """
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    if not token:
        token = request.query_params.get("token")

    if not token:
        raise CredentialsValidationException()

    payload = decode_access_token(token)
    if not payload:
        raise CredentialsValidationException()
    email = payload.get("sub")
    if not email:
        raise CredentialsValidationException()

    user = db.query(UserModel).filter(UserModel.email == email).first()
    if not user or not user.is_active:
        raise CredentialsValidationException()

    file_path = os.path.join("storage", "exports", str(user.id), filename)

    resolved_path = os.path.normpath(os.path.abspath(file_path))
    expected_prefix = os.path.normpath(os.path.abspath(os.path.join("storage", "exports", str(user.id))))
    if not os.path.normcase(resolved_path).startswith(os.path.normcase(expected_prefix)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export file not found")

    return FileResponse(file_path, filename=filename)



