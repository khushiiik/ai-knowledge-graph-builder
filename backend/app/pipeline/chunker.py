from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_documents(
    documents: List[Document], 
    chunk_size: int = 1200, 
    chunk_overlap: int = 200
) -> List[Document]:
    """
    Chunks a list of LangChain documents using RecursiveCharacterTextSplitter.
    Uses chunk_size=1200 and chunk_overlap=200 to preserve full table rows and multi-line records.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    return splitter.split_documents(documents)

