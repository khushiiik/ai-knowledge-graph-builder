import os
import uuid
from uuid import UUID
from typing import List
import qdrant_client
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

# Patch QdrantClient to support the legacy search method used by langchain_community
if not hasattr(qdrant_client.QdrantClient, "search"):
    def legacy_search(self, collection_name, query_vector, query_filter=None, search_params=None, limit=10, offset=0, with_payload=True, with_vectors=False, score_threshold=None, consistency=None, **kwargs):
        return self.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            search_params=search_params,
            limit=limit,
            offset=offset,
            with_payload=with_payload,
            with_vectors=with_vectors,
            score_threshold=score_threshold,
            consistency=consistency,
            **kwargs
        ).points
    qdrant_client.QdrantClient.search = legacy_search

from langchain_community.vectorstores import Qdrant
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from sqlalchemy.orm import Session

from typing import List, Optional

from app.config import settings
from app.pipeline.extractor import extract_documents_from_file
from app.pipeline.chunker import chunk_documents
from app.pipeline.embedder import get_embedding_model
from app.models.document import Document as DocumentModel
from app.models.chunk import Chunk

COLLECTION_NAME = "shared_knowledge_graph"

def _update_job_progress(db: Session, job_id: Optional[UUID], progress: int, current_step: str, status: Optional[str] = None):
    if not job_id:
        return
    from app.models.processing_job import ProcessingJob
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if job:
        job.progress = progress
        job.current_step = current_step
        if status:
            job.status = status
        db.commit()

def ensure_collection_exists(client: QdrantClient, collection_name: str, vector_size: int = 3072) -> None:
    """
    Checks if a collection exists in Qdrant. If not, or if its dimension size
    does not match the target vector_size, recreates it manually.
    """
    try:
        info = client.get_collection(collection_name=collection_name)
        # Check if the existing collection vectors size matches
        current_size = info.config.params.vectors.size
        if current_size != vector_size:
            client.delete_collection(collection_name=collection_name)
            client.create_collection(
                collection_name=collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=vector_size,
                    distance=qdrant_models.Distance.COSINE
                )
            )
    except Exception:
        # Collection does not exist, create it manually
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=vector_size,
                distance=qdrant_models.Distance.COSINE
            )
        )

def ingest_document_to_qdrant(db: Session, document_id: UUID, file_path: str, mime_type: str, tenant_id: int, job_id: Optional[UUID] = None) -> None:
    """
    Ingestion pipeline:
    1. Extracts documents/text from a file.
    2. Stores the raw extracted text on the Document record in Postgres.
    3. Chunks the documents.
    4. Generates matching IDs and stores the Chunk records in Postgres.
    5. Tags chunks with tenant_id for multi-tenant isolation.
    6. Connects to Qdrant and stores the vector embeddings using the matching IDs.
    """
    # 1. Extract text content
    _update_job_progress(db, job_id, 10, "Extracting text content from file", "PROCESSING")
    docs = extract_documents_from_file(file_path, mime_type)
    if not docs:
        return

    # 2. Update Document record with raw extracted text in Postgres
    _update_job_progress(db, job_id, 30, "Saving raw text to database")
    raw_text = "\n".join([doc.page_content for doc in docs])
    db_doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if db_doc:
        db_doc.raw_text = raw_text
        db.commit()

    # 3. Chunk text
    _update_job_progress(db, job_id, 50, "Chunking document text")
    chunks = chunk_documents(docs, chunk_size=500, chunk_overlap=100)

    # 4. Generate IDs and save Chunk entities to Postgres
    _update_job_progress(db, job_id, 70, "Persisting chunks to database")
    postgres_chunks = []
    qdrant_ids = []
    for idx, chunk in enumerate(chunks):
        chunk_id = uuid.uuid4()
        
        # Attach tenant_id and metadata for security/filtering
        chunk.metadata["tenant_id"] = tenant_id
        chunk.metadata["source_file"] = os.path.basename(file_path)

        page = chunk.metadata.get("page")
        page_section = f"Page {page + 1}" if page is not None else None

        postgres_chunk = Chunk(
            id=chunk_id,
            document_id=document_id,
            user_id=tenant_id,
            chunk_index=idx,
            text=chunk.page_content,
            source_filename=os.path.basename(file_path),
            page_section=page_section,
            qdrant_point_id=str(chunk_id)
        )
        postgres_chunks.append(postgres_chunk)
        qdrant_ids.append(str(chunk_id))

    db.add_all(postgres_chunks)
    db.commit()

    # 5. Index vector embeddings in Qdrant
    _update_job_progress(db, job_id, 90, "Indexing vector embeddings in Qdrant")
    embeddings = get_embedding_model()

    # Store in Qdrant Vector Store
    qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
    client = QdrantClient(url=qdrant_url)
    
    # Ensure collection exists to bypass the LangChain recreate compatibility bug
    ensure_collection_exists(client, COLLECTION_NAME, vector_size=3072)
    
    vector_store = Qdrant(
        client=client,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings
    )
    
    vector_store.add_documents(
        documents=chunks,
        ids=qdrant_ids
    )

    # 6. Extract entities & relationships per chunk and write them into Neo4j,
    # tagged with tenant_id so graph search stays isolated per user (same
    # pattern as the tenant_id filter used for Qdrant above).
    _update_job_progress(db, job_id, 97, "Extracting entities and relationships into Neo4j")
    from app.pipeline.ner import extract_entities_and_relations
    from app.db.neo4j_client import write_graph_data

    for chunk in chunks:
        try:
            extraction = extract_entities_and_relations(chunk.page_content)
            write_graph_data(
                user_id=tenant_id,
                source_filename=os.path.basename(file_path),
                entities=extraction["entities"],
                relationships=extraction["relationships"],
            )
        except Exception:
            # Graph extraction is best-effort -- one bad chunk shouldn't fail the whole pipeline
            continue

def get_tenant_retriever(tenant_id: int, limit: int = 3, source_file: Optional[str] = None) -> VectorStoreRetriever:
    """
    Returns a Qdrant-backed VectorStoreRetriever pre-filtered for a specific tenant_id.
    Ensures that users can only query their own files.
    """
    embeddings = get_embedding_model()
    qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"

    client = QdrantClient(url=qdrant_url)
    
    # Ensure collection exists for retrieval too
    ensure_collection_exists(client, COLLECTION_NAME, vector_size=3072)

    vector_store = Qdrant(
        client=client,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings
    )

    # Define Qdrant payload filter to enforce multi-tenancy boundaries
    must_conditions = [
        qdrant_models.FieldCondition(
            key="metadata.tenant_id",
            match=qdrant_models.MatchValue(value=tenant_id)
        )
    ]
    if source_file:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="metadata.source_file",
                match=qdrant_models.MatchValue(value=source_file)
            )
        )
    tenant_filter = qdrant_models.Filter(must=must_conditions)

    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={
            "filter": tenant_filter,
            "k": limit
        }
    )