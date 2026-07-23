import os
import uuid
import pandas as pd
from uuid import UUID
from typing import List
import qdrant_client
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from app.models.processing_job import ProcessingJob
from app.pipeline.ner import extract_entities_and_relations
from app.db.neo4j_client import write_graph_data

# Patch QdrantClient to support the legacy search method used by langchain_community
if not hasattr(qdrant_client.QdrantClient, "search"):

    def legacy_search(
        self,
        collection_name,
        query_vector,
        query_filter=None,
        search_params=None,
        limit=10,
        offset=0,
        with_payload=True,
        with_vectors=False,
        score_threshold=None,
        consistency=None,
        **kwargs,
    ):
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
            **kwargs,
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


def _update_job_progress(
    db: Session,
    job_id: Optional[UUID],
    progress: int,
    current_step: str,
    status: Optional[str] = None,
):
    if not job_id:
        return
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if job:
        job.progress = progress
        job.current_step = current_step
        if status:
            job.status = status
        db.commit()


def ensure_collection_exists(
    client: QdrantClient, collection_name: str, vector_size: int = 3072
) -> None:
    """
    Checks if a collection exists in Qdrant. If not, or if its dimension size
    does not match the target vector_size, recreates it manually.
    """
    try:
        collection_info = client.get_collection(collection_name=collection_name)
        # Check if the existing collection vectors size matches
        current_vector_size = collection_info.config.params.vectors.size
        if current_vector_size != vector_size:
            client.delete_collection(collection_name=collection_name)
            client.create_collection(
                collection_name=collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=vector_size, distance=qdrant_models.Distance.COSINE
                ),
            )
    except Exception:
        # Collection does not exist, create it manually
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=vector_size, distance=qdrant_models.Distance.COSINE
            ),
        )


def generate_dataset_profile(file_path: str) -> dict:
    if file_path.endswith((".xlsx", ".xls")):
        dataframe = pd.read_excel(file_path)
    else:
        dataframe = pd.read_csv(file_path)

    row_count = len(dataframe)
    column_count = len(dataframe.columns)
    columns = []
    statistics = {}
    text_columns = []

    for column_name in dataframe.columns:
        column_type = str(dataframe[column_name].dtype)
        if "int" in column_type or "float" in column_type:
            inferred_type = "numeric"
            role = "measure"
            try:
                statistics[str(column_name)] = {
                    "min": float(dataframe[column_name].min()),
                    "max": float(dataframe[column_name].max()),
                    "mean": float(dataframe[column_name].mean()),
                }
            except Exception:
                pass
        elif "datetime" in column_type or "date" in str(column_name).lower():
            inferred_type = "datetime"
            role = "time"
        else:
            inferred_type = "categorical"
            role = "dimension"
            try:
                mean_length = dataframe[column_name].astype(str).str.len().mean()
                if mean_length > 40:
                    inferred_type = "text"
                    role = "semantic"
                    text_columns.append(str(column_name))
            except Exception:
                pass

        columns.append({"name": str(column_name), "type": inferred_type, "role": role})

    has_text = len(text_columns) > 0

    has_numeric = False
    for col in columns:
        if col["type"] == "numeric":
            has_numeric = True
            break

    has_columns = len(columns) > 0

    return {
        "version": 1,
        "row_count": row_count,
        "column_count": column_count,
        "columns": columns,
        "statistics": statistics,
        "text_columns": text_columns,
        "supports": {
            "semantic_search": has_text,
            "visualization": has_columns,
            "aggregation": has_numeric,
        },
    }


def ingest_document_to_qdrant(
    db: Session,
    document_id: UUID,
    file_path: str,
    mime_type: str,
    tenant_id: int,
    job_id: Optional[UUID] = None,
) -> None:
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
    _update_job_progress(
        db, job_id, 10, "Extracting text content from file", "PROCESSING"
    )
    extracted_documents = extract_documents_from_file(file_path, mime_type)
    if not extracted_documents:
        return

    # Sanitize document text to prevent ValueError: A string literal cannot contain NUL (0x00) characters.
    for document in extracted_documents:
        if document.page_content:
            document.page_content = document.page_content.replace("\x00", "").replace(
                "\u0000", ""
            )

    # 2. Update Document record with raw extracted text in Postgres
    _update_job_progress(db, job_id, 30, "Saving raw text to database")
    db_document = (
        db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    )
    if db_document:
        file_type_lower = db_document.file_type.lower()
        if file_type_lower in ("csv", "xlsx", "xls"):
            try:
                dataset_profile = generate_dataset_profile(file_path)
                db_document.dataset_profile = dataset_profile
                db_document.embedding_status = "NOT_STARTED"
                db_document.raw_text = None
                db.commit()
                _update_job_progress(
                    db,
                    job_id,
                    100,
                    "Spreadsheet dataset profiled successfully (Lazy indexing enabled)",
                    "COMPLETED",
                )
                return
            except Exception as error:
                db_document.raw_text = f"Profiling failed: {str(error)}"
                db.commit()
                _update_job_progress(
                    db, job_id, 100, f"Profiling failed: {str(error)}", "FAILED"
                )
                return
        else:
            raw_text_parts = []
            for doc in extracted_documents:
                raw_text_parts.append(doc.page_content)
            raw_text = "\n".join(raw_text_parts)
            db_document.raw_text = raw_text
            db.commit()

    # 3. Chunk text
    _update_job_progress(db, job_id, 50, "Chunking document text")
    chunks = chunk_documents(extracted_documents, chunk_size=1200, chunk_overlap=200)

    # 4. Generate IDs and save Chunk entities to Postgres
    _update_job_progress(db, job_id, 70, "Persisting chunks to database")
    postgres_chunks = []
    qdrant_point_ids = []
    for chunk_index, chunk_document in enumerate(chunks):
        chunk_id = uuid.uuid4()

        # Attach tenant_id and metadata for security/filtering
        chunk_document.metadata["tenant_id"] = tenant_id
        chunk_document.metadata["source_file"] = os.path.basename(file_path)

        page_number = chunk_document.metadata.get("page")
        page_section_label = (
            f"Page {page_number + 1}" if page_number is not None else None
        )

        new_postgres_chunk = Chunk(
            id=chunk_id,
            document_id=document_id,
            user_id=tenant_id,
            chunk_index=chunk_index,
            text=chunk_document.page_content,
            source_filename=os.path.basename(file_path),
            page_section=page_section_label,
            qdrant_point_id=str(chunk_id),
        )
        postgres_chunks.append(new_postgres_chunk)
        qdrant_point_ids.append(str(chunk_id))

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
        client=client, collection_name=COLLECTION_NAME, embeddings=embeddings
    )

    vector_store.add_documents(documents=chunks, ids=qdrant_point_ids)

    # 6. Extract entities & relationships per chunk and write them into Neo4j
    _update_job_progress(
        db, job_id, 97, "Extracting entities and relationships into Neo4j"
    )

    for chunk_document in chunks:
        try:
            extraction = extract_entities_and_relations(chunk_document.page_content)
            write_graph_data(
                user_id=tenant_id,
                source_filename=os.path.basename(file_path),
                entities=extraction["entities"],
                relationships=extraction["relationships"],
            )
        except Exception:
            # Graph extraction is best-effort -- one bad chunk shouldn't fail the whole pipeline
            continue


def get_tenant_retriever(
    tenant_id: int, limit: int = 3, source_file: Optional[str] = None
) -> VectorStoreRetriever:
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
        client=client, collection_name=COLLECTION_NAME, embeddings=embeddings
    )

    # Define Qdrant payload filter to enforce multi-tenancy boundaries
    filter_conditions = [
        qdrant_models.FieldCondition(
            key="metadata.tenant_id", match=qdrant_models.MatchValue(value=tenant_id)
        )
    ]
    if source_file:
        filter_conditions.append(
            qdrant_models.FieldCondition(
                key="metadata.source_file",
                match=qdrant_models.MatchValue(value=source_file),
            )
        )
    tenant_filter = qdrant_models.Filter(must=filter_conditions)

    return vector_store.as_retriever(
        search_type="similarity", search_kwargs={"filter": tenant_filter, "k": limit}
    )


def run_lazy_indexing(db: Session, document_id: UUID, tenant_id: int) -> None:
    """
    Performs chunking, embedding generation, and Qdrant storage only for the text/semantic columns
    of a spreadsheet on-demand.
    """
    db_document = (
        db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    )
    if not db_document:
        return

    file_path = db_document.storage_path
    dataset_profile = db_document.dataset_profile or {}
    text_columns = dataset_profile.get("text_columns", [])

    if file_path.endswith((".xlsx", ".xls")):
        dataframe = pd.read_excel(file_path)
    else:
        dataframe = pd.read_csv(file_path)

    # Fallback to all categorical columns if no text columns found
    if not text_columns:
        text_columns = []
        for column_name in dataframe.columns:
            if str(dataframe[column_name].dtype) in ("object", "string"):
                text_columns.append(column_name)
    if not text_columns:
        text_columns = list(dataframe.columns)

    # Chunk in row groups of 50
    chunk_size_rows = 50
    chunks = []
    for start_row_index in range(0, len(dataframe), chunk_size_rows):
        dataframe_subset = dataframe.iloc[
            start_row_index : start_row_index + chunk_size_rows
        ]
        lines = []
        for row_index, row_data in dataframe_subset.iterrows():
            parts = []
            for column_name in text_columns:
                if pd.notna(row_data[column_name]):
                    parts.append(f"{column_name}: {row_data[column_name]}")
            if parts:
                lines.append(" | ".join(parts))
        if lines:
            chunk_text = (
                f"File: {db_document.original_filename}\nRows {start_row_index} to {start_row_index + len(dataframe_subset) - 1}\n"
                + "\n".join(lines)
            )
            chunks.append(
                Document(page_content=chunk_text, metadata={"source": file_path})
            )

    if not chunks:
        db_document.embedding_status = "READY"
        db.commit()
        return

    postgres_chunks = []
    qdrant_point_ids = []
    for chunk_index, chunk_document in enumerate(chunks):
        chunk_id = uuid.uuid4()
        chunk_document.metadata["tenant_id"] = tenant_id
        chunk_document.metadata["source_file"] = os.path.basename(file_path)

        new_postgres_chunk = Chunk(
            id=chunk_id,
            document_id=document_id,
            user_id=tenant_id,
            chunk_index=chunk_index,
            text=chunk_document.page_content,
            source_filename=os.path.basename(file_path),
            page_section=f"Rows {chunk_index * chunk_size_rows} to {(chunk_index + 1) * chunk_size_rows}",
            qdrant_point_id=str(chunk_id),
        )
        postgres_chunks.append(new_postgres_chunk)
        qdrant_point_ids.append(str(chunk_id))

    db.add_all(postgres_chunks)
    db.commit()

    embeddings = get_embedding_model()
    qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
    client = QdrantClient(url=qdrant_url)
    ensure_collection_exists(client, COLLECTION_NAME, vector_size=3072)

    vector_store = Qdrant(
        client=client, collection_name=COLLECTION_NAME, embeddings=embeddings
    )
    vector_store.add_documents(documents=chunks, ids=qdrant_point_ids)

    # Set status to READY
    db_document.embedding_status = "READY"
    db.commit()
