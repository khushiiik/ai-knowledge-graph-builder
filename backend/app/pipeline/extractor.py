import os
import csv
import json
import zipfile
import xml.etree.ElementTree as ET
from typing import List
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader

def extract_docx_text(file_path: str) -> str:
    """Extracts text from a .docx file preserving paragraph layout."""
    try:
        with zipfile.ZipFile(file_path) as docx:
            xml_content = docx.read('word/document.xml')
        root = ET.fromstring(xml_content)
        
        paragraphs = []
        for p_elem in root.iter():
            if p_elem.tag.endswith('}p'):
                p_text = []
                for t_elem in p_elem.iter():
                    if t_elem.tag.endswith('}t') and t_elem.text:
                        p_text.append(t_elem.text)
                if p_text:
                    paragraphs.append("".join(p_text))
        return "\n".join(paragraphs)
    except Exception as e:
        raise ValueError(f"Failed to parse docx file: {str(e)}")

def extract_xlsx_text(file_path: str) -> str:
    """Extracts text from a .xlsx file using shared strings and sheet values."""
    try:
        texts = []
        with zipfile.ZipFile(file_path) as xlsx:
            if 'xl/sharedStrings.xml' in xlsx.namelist():
                xml_content = xlsx.read('xl/sharedStrings.xml')
                root = ET.fromstring(xml_content)
                for elem in root.iter():
                    if elem.tag.endswith('}t'):
                        if elem.text:
                            texts.append(elem.text)
            for name in xlsx.namelist():
                if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                    xml_content = xlsx.read(name)
                    root = ET.fromstring(xml_content)
                    for elem in root.iter():
                        if elem.tag.endswith('}v'):
                            if elem.text:
                                texts.append(elem.text)
        return "\n".join(texts)
    except Exception as e:
        raise ValueError(f"Failed to parse xlsx file: {str(e)}")

def extract_documents_from_file(file_path: str, mime_type: str = None) -> List[Document]:
    """
    Extracts contents from a file and returns a list of LangChain Document objects.
    Supports PDF, DOCX, XLSX, TXT, CSV, JSON, and Markdown.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path.lower())[1]

    # 1. PDF
    if ext == ".pdf" or mime_type == "application/pdf":
        loader = PyPDFLoader(file_path)
        return loader.load()

    # 2. DOCX
    elif ext == ".docx" or mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        content = extract_docx_text(file_path)
        return [Document(page_content=content, metadata={"source": file_path})]

    # 3. XLSX
    elif ext == ".xlsx" or mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        content = extract_xlsx_text(file_path)
        return [Document(page_content=content, metadata={"source": file_path})]

    # 4. Text / Markdown
    elif ext in (".txt", ".md", ".markdown") or (mime_type and mime_type.startswith("text/")):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return [Document(page_content=content, metadata={"source": file_path})]

    # 5. CSV
    elif ext == ".csv" or mime_type in ("text/csv", "application/csv"):
        rows = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(", ".join(row))
        content = "\n".join(rows)
        return [Document(page_content=content, metadata={"source": file_path})]

    # 6. JSON
    elif ext == ".json" or mime_type == "application/json":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        content = json.dumps(data, indent=2)
        return [Document(page_content=content, metadata={"source": file_path})]

    # Fallback
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return [Document(page_content=content, metadata={"source": file_path})]
        except Exception as e:
            raise ValueError(f"Unsupported file format for extraction: {ext} (Error: {str(e)})")
