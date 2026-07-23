from typing import Dict, List, Optional

from app.pipeline.pipeline_runner import get_tenant_retriever


def retrieve_chunks(
    query: str, tenant_id: int, limit: int = 4, source_file: Optional[str] = None
) -> List[Dict]:
    """
    Embeds `query` and fetches the top-k most similar chunks previously stored
    in Qdrant during document ingestion, scoped to this user's tenant_id so
    users never see each other's documents.

    If `source_file` is set (conversation is "locked" to one document) but that
    filtered search comes back empty, we retry unfiltered across all of the
    user's documents. Without this, a conversation locked onto doc A returns
    nothing for a question that's actually answered in doc B -- it looks like
    the retriever is broken when really it's just filtered too narrowly.
    """
    retrieved_documents = _search(query, tenant_id, limit, source_file)

    if not retrieved_documents and source_file:
        retrieved_documents = _search(query, tenant_id, limit, source_file=None)

    formatted_results = []
    for document in retrieved_documents:
        formatted_results.append(
            {
                "text": document.page_content,
                "source": document.metadata.get("source_file", "unknown"),
                "page": document.metadata.get("page"),
                "type": "semantic",
            }
        )
    return formatted_results


def _search(query: str, tenant_id: int, limit: int, source_file: Optional[str]):
    retriever = get_tenant_retriever(
        tenant_id=tenant_id, limit=limit, source_file=source_file
    )
    try:
        return retriever.invoke(query)
    except Exception:
        # Qdrant collection may not exist yet if the user hasn't uploaded anything
        return []


def build_context_block(chunks: List[Dict]) -> str:
    """Joins retrieved chunks into one context string, tagging each with its source file."""
    if not chunks:
        return ""

    context_blocks = []
    for chunk in chunks:
        context_blocks.append(f"[Source: {chunk['source']}]\n{chunk['text']}")

    return "\n\n---\n\n".join(context_blocks)
