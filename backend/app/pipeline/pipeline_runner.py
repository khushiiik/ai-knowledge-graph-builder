import os
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from langchain_community.vectorstores import Qdrant
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

from app.config import settings
from app.pipeline.extractor import extract_documents_from_file
from app.pipeline.chunker import chunk_documents
from app.pipeline.embedder import get_embedding_model

COLLECTION_NAME = "shared_knowledge_graph"

def ensure_collection_exists(client: QdrantClient, collection_name: str, vector_size: int = 384) -> None:
    """
    Checks if a collection exists in Qdrant. If not, creates it manually.
    Bypasses LangChain's recreate_collection call which throws an compatibility error in qdrant-client >= 1.18.
    """
    try:
        client.get_collection(collection_name=collection_name)
    except Exception:
        # Collection does not exist, create it manually with Cosine distance and 384 dimensions (sentence-transformers size)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=vector_size,
                distance=qdrant_models.Distance.COSINE
            )
        )

def ingest_document_to_qdrant(file_path: str, mime_type: str, tenant_id: int) -> None:
    """
    Ingestion pipeline:
    1. Extracts documents/text from a file.
    2. Chunks the documents.
    3. Tags chunks with tenant_id for multi-tenant isolation.
    4. Connects to Qdrant and stores the vector embeddings.
    """
    # Extract text content
    docs = extract_documents_from_file(file_path, mime_type)
    if not docs:
        return

    # Chunk text
    chunks = chunk_documents(docs, chunk_size=500, chunk_overlap=100)

    # Attach tenant_id and metadata for security/filtering
    for chunk in chunks:
        chunk.metadata["tenant_id"] = tenant_id
        chunk.metadata["source_file"] = os.path.basename(file_path)

    # Load embeddings
    embeddings = get_embedding_model()

    # Store in Qdrant Vector Store
    qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
    client = QdrantClient(url=qdrant_url)
    
    # Ensure collection exists to bypass the LangChain recreate compatibility bug
    ensure_collection_exists(client, COLLECTION_NAME, vector_size=384)
    
    Qdrant.from_documents(
        documents=chunks,
        embedding=embeddings,
        url=qdrant_url,
        collection_name=COLLECTION_NAME,
        prefer_grpc=False
    )

def get_tenant_retriever(tenant_id: int, limit: int = 3) -> VectorStoreRetriever:
    """
    Returns a Qdrant-backed VectorStoreRetriever pre-filtered for a specific tenant_id.
    Ensures that users can only query their own files.
    """
    embeddings = get_embedding_model()
    qdrant_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"

    client = QdrantClient(url=qdrant_url)
    
    # Ensure collection exists for retrieval too
    ensure_collection_exists(client, COLLECTION_NAME, vector_size=384)

    vector_store = Qdrant(
        client=client,
        collection_name=COLLECTION_NAME,
        embeddings=embeddings
    )

    # Define Qdrant payload filter to enforce multi-tenancy boundaries
    tenant_filter = qdrant_models.Filter(
        must=[
            qdrant_models.FieldCondition(
                key="metadata.tenant_id",
                match=qdrant_models.MatchValue(value=tenant_id)
            )
        ]
    )

    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={
            "filter": tenant_filter,
            "k": limit
        }
    )
