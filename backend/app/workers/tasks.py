import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.workers.celery_app import celery_app
from app.dependencies import SessionLocal
from app.models.processing_job import ProcessingJob, ProcessingJobStatus
from app.models.document import Document, DocumentStatus
from app.pipeline.pipeline_runner import ingest_document_to_qdrant

@celery_app.task(name="app.workers.tasks.ingest_document_task")
def ingest_document_task(job_id_str: str, document_id_str: str, file_path: str, mime_type: str, tenant_id: int):
    db: Session = SessionLocal()
    job_id = uuid.UUID(job_id_str)
    document_id = uuid.UUID(document_id_str)
    
    try:
        # Run ingestion pipeline (which updates ProcessingJob step/progress details)
        ingest_document_to_qdrant(
            db=db,
            document_id=document_id,
            file_path=file_path,
            mime_type=mime_type,
            tenant_id=tenant_id,
            job_id=job_id
        )
        
        # Update Document and Job status to completed
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.READY.value
            doc.processed_at = func.now()
        
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if job:
            job.status = ProcessingJobStatus.COMPLETED.value
            job.progress = 100
            job.current_step = "Completed"
            job.finished_at = func.now()
            
        db.commit()
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        # Update Document and Job status to failed
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = DocumentStatus.FAILED.value
            
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if job:
            job.status = ProcessingJobStatus.FAILED.value
            job.error_message = str(e)
            job.finished_at = func.now()
            
        db.commit()
    finally:
        db.close()
