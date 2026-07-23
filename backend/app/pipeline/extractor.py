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
            xml_content = docx.read("word/document.xml")
        root = ET.fromstring(xml_content)

        paragraphs = []
        for paragraph_element in root.iter():
            if paragraph_element.tag.endswith("}p"):
                paragraph_text = []
                for text_element in paragraph_element.iter():
                    if text_element.tag.endswith("}t") and text_element.text:
                        paragraph_text.append(text_element.text)
                if paragraph_text:
                    paragraphs.append("".join(paragraph_text))
        return "\n".join(paragraphs)
    except Exception as error:
        raise ValueError(f"Failed to parse docx file: {str(error)}")


def extract_xlsx_text(file_path: str) -> str:
    """Extracts text from a .xlsx file using shared strings and sheet values."""
    try:
        texts = []
        with zipfile.ZipFile(file_path) as xlsx:
            if "xl/sharedStrings.xml" in xlsx.namelist():
                xml_content = xlsx.read("xl/sharedStrings.xml")
                root = ET.fromstring(xml_content)
                for xml_element in root.iter():
                    if xml_element.tag.endswith("}t"):
                        if xml_element.text:
                            texts.append(xml_element.text)
            for name in xlsx.namelist():
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    xml_content = xlsx.read(name)
                    root = ET.fromstring(xml_content)
                    for xml_element in root.iter():
                        if xml_element.tag.endswith("}v"):
                            if xml_element.text:
                                texts.append(xml_element.text)
        return "\n".join(texts)
    except Exception as error:
        raise ValueError(f"Failed to parse xlsx file: {str(error)}")


def extract_documents_from_file(
    file_path: str, mime_type: str = None
) -> List[Document]:
    """
    Extracts contents from a file and returns a list of LangChain Document objects.
    Supports PDF, DOCX, XLSX, TXT, CSV, JSON, and Markdown.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_extension = os.path.splitext(file_path.lower())[1]

    # 1. PDF
    if file_extension == ".pdf" or mime_type == "application/pdf":
        loader = PyPDFLoader(file_path)
        return loader.load()

    # 2. DOCX
    elif (
        file_extension == ".docx"
        or mime_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        content = extract_docx_text(file_path)
        return [Document(page_content=content, metadata={"source": file_path})]

    # 3. XLSX
    elif (
        file_extension == ".xlsx"
        or mime_type
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ):
        content = extract_xlsx_text(file_path)
        return [Document(page_content=content, metadata={"source": file_path})]

    # 4. Text / Markdown
    elif file_extension in (".txt", ".md", ".markdown") or (
        mime_type and mime_type.startswith("text/")
    ):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file_handle:
            content = file_handle.read()
        return [Document(page_content=content, metadata={"source": file_path})]

    # 5. CSV
    elif file_extension == ".csv" or mime_type in ("text/csv", "application/csv"):
        rows = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file_handle:
            reader = csv.reader(file_handle)
            for row in reader:
                rows.append(", ".join(row))
        content = "\n".join(rows)
        return [Document(page_content=content, metadata={"source": file_path})]

    # 6. JSON
    elif file_extension == ".json" or mime_type == "application/json":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file_handle:
            data = json.load(file_handle)
        content = json.dumps(data, indent=2)
        return [Document(page_content=content, metadata={"source": file_path})]

    # Fallback
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as file_handle:
                content = file_handle.read()
            return [Document(page_content=content, metadata={"source": file_path})]
        except Exception as error:
            raise ValueError(
                f"Unsupported file format for extraction: {file_extension} (Error: {str(error)})"
            )
