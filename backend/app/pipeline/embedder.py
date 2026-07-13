from langchain_community.embeddings import FastEmbedEmbeddings

def get_embedding_model() -> FastEmbedEmbeddings:
    """
    Returns an instance of FastEmbedEmbeddings pre-configured to run locally via ONNX Runtime.
    Extremely fast, requires no PyTorch, and avoids region-specific Hugging Face API DNS blocks.
    """
    return FastEmbedEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
