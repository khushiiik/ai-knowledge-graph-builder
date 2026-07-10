import os
import csv
import json
from typing import List
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader

def extract_documents_from_file(file_path: str, mime_type: str = None) -> List[Document]:
    """
    Extracts contents from a file and returns a list of LangChain Document objects.
    Supports PDF, TXT, CSV, JSON, and Markdown.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path.lower())[1]

    # 1. PDF
    if ext == ".pdf" or mime_type == "application/pdf":
        loader = PyPDFLoader(file_path)
        return loader.load()

    # 2. Text / Markdown
    elif ext in (".txt", ".md", ".markdown") or (mime_type and mime_type.startswith("text/")):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return [Document(page_content=content, metadata={"source": file_path})]

    # 3. CSV
    elif ext == ".csv" or mime_type in ("text/csv", "application/csv"):
        rows = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(", ".join(row))
        content = "\n".join(rows)
        return [Document(page_content=content, metadata={"source": file_path})]

    # 4. JSON
    elif ext == ".json" or mime_type == "application/json":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        content = json.dumps(data, indent=2)
        return [Document(page_content=content, metadata={"source": file_path})]

    # 5. Fallback read
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return [Document(page_content=content, metadata={"source": file_path})]
        except Exception as e:
            raise ValueError(f"Unsupported file format for extraction: {ext} (Error: {str(e)})")
