from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_documents(
    documents: List[Document], 
    chunk_size: int = 500, 
    chunk_overlap: int = 100
) -> List[Document]:
    """
    Chunks a list of LangChain documents using RecursiveCharacterTextSplitter.
    Uses chunk_size=500 and chunk_overlap=100 for high-accuracy context matching.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    return splitter.split_documents(documents)
