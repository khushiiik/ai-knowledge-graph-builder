from typing import Dict, List, Optional

from app.pipeline.pipeline_runner import get_tenant_retriever


def retrieve_chunks(query: str, tenant_id: int, limit: int = 4, source_file: Optional[str] = None) -> List[Dict]:
    """
    Embeds `query` and fetches the top-k most similar chunks previously stored
    in Qdrant during document ingestion, scoped to this user's tenant_id so
    users never see each other's documents.
    """
    retriever = get_tenant_retriever(tenant_id=tenant_id, limit=limit, source_file=source_file)
    try:
        docs = retriever.invoke(query)
    except Exception:
        # Qdrant collection may not exist yet if the user hasn't uploaded anything
        docs = []

    return [
        {"text": doc.page_content, "source": doc.metadata.get("source_file", "unknown")}
        for doc in docs
    ]


def build_context_block(chunks: List[Dict]) -> str:
    """Joins retrieved chunks into one context string, tagging each with its source file."""
    if not chunks:
        return ""
    return "\n\n---\n\n".join(f"[Source: {c['source']}]\n{c['text']}" for c in chunks)
