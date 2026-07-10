from langchain_community.embeddings import HuggingFaceEmbeddings

def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    Returns an instance of HuggingFaceEmbeddings pre-configured to run
    sentence-transformers/all-MiniLM-L6-v2 locally.
    """
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
