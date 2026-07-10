from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.dependencies import get_db, get_current_active_user
from app.models.user import User as UserModel
from app.models.document import Document as DocumentModel, DocumentStatus
from app.schemas.document import DocumentRead
from app.utils.file_storage import save_upload_file, delete_stored_file
from app.validators.upload_validator import validate_uploaded_file

from app.pipeline.pipeline_runner import ingest_document_to_qdrant

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
) -> DocumentModel:
    """Upload a file, validate it, and create a document record."""
    # Perform strict validators check (sizes, types, etc.)
    validate_uploaded_file(file, request)

    try:
        # Save file to storage
        stored_filename, storage_path, file_size, checksum = save_upload_file(file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}"
        )

    # Determine file type / extension
    file_type = file.filename.split(".")[-1] if file.filename and "." in file.filename else "unknown"
    mime_type = file.content_type or "application/octet-stream"

    # Create model record with initial UPLOADING status
    new_doc = DocumentModel(
        user_id=current_user.id,
        original_filename=file.filename or "unknown",
        stored_filename=stored_filename,
        storage_path=storage_path,
        file_type=file_type,
        mime_type=mime_type,
        file_size=file_size,
        checksum=checksum,
        status=DocumentStatus.UPLOADING.value
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    # Run ingestion pipeline to index vector embeddings in Qdrant
    try:
        ingest_document_to_qdrant(
            file_path=storage_path,
            mime_type=mime_type,
            tenant_id=current_user.id
        )
        new_doc.status = DocumentStatus.READY.value
        new_doc.processed_at = func.now()
        db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
        new_doc.status = DocumentStatus.FAILED.value
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document upload succeeded, but vector database indexing failed: {str(e)}"
        )

    return new_doc

@router.get("", response_model=List[DocumentRead])
def list_documents(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
) -> List[DocumentModel]:
    """List all active (non-deleted) documents for the current active user."""
    return db.query(DocumentModel).filter(
        DocumentModel.user_id == current_user.id,
        DocumentModel.deleted_at.is_(None)
    ).all()

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    
    return {
        "id": doc.id,
        "status": doc.status,
        "processed_at": doc.processed_at,
        "deleted_at": doc.deleted_at
    }

@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_active_user)
):
    """Soft delete a document (updates status to DELETED and deletes the file from local storage)."""
    doc = db.query(DocumentModel).filter(
        DocumentModel.id == document_id,
        DocumentModel.user_id == current_user.id,
        DocumentModel.deleted_at.is_(None)
    ).first()
    
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Delete physical file from storage
    delete_stored_file(doc.storage_path)

    # Perform soft delete in database
    doc.status = DocumentStatus.DELETED.value
    doc.deleted_at = func.now()
    db.commit()

    return {"message": "Document deleted successfully"}
