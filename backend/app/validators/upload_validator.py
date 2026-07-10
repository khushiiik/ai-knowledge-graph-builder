import os
from fastapi import UploadFile, HTTPException, Request, status

MAX_FILE_SIZE_MB = 51
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".csv",
    ".xlsx",
    ".json",
    ".md",
    ".markdown",
}

# Allowed mime types
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/csv",
    "application/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/json",
    "text/markdown",
    "text/x-markdown",
}


def validate_uploaded_file(file: UploadFile, request: Request = None) -> None:
    """
    Validates the uploaded file size and content type.

    1. Early rejection using Content-Length request headers.
    2. Physical size verification via chunking (defends against fake headers and keeps memory footprint low).
    3. Whitelists file extensions and MIME types.
    """
    # 1. Early Content-Length Validation
    if request:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File size exceeds the {MAX_FILE_SIZE_MB - 1}MB limit (via Content-Length).",
                    )
            except ValueError:
                pass

    # 2. Extension validation
    filename = file.filename or ""
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not allowed. Supported formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # 3. MIME type validation
    mime_type = file.content_type
    if not mime_type or mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME type '{mime_type}' is not allowed. Supported formats: PDF, DOCX, TXT, CSV, XLSX, JSON, Markdown.",
        )

    # 4. Chunk validation (Safety check against fake/altered Content-Length headers)
    # Stream the file to ensure memory consumption stays extremely low
    file.file.seek(0)
    total_size = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    while chunk := file.file.read(chunk_size):
        total_size += len(chunk)
        if total_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size physically exceeds the {MAX_FILE_SIZE_MB}MB limit.",
            )

    # Reset seek pointer for next operations
    file.file.seek(0)


# Multi-Tenancy Collection Sharing architectural guidelines:
#
# To isolate user data safely within one single shared collection in Qdrant:
# 1. Separate documents by appending a payload filter, e.g., 'tenant_id': user_id (or user_id directly).
# 2. Inject this filter into a Search Wrapper. When performing search queries:
#
#    def search_tenant_documents(query_vector, tenant_id: int, top_k: int = 5):
#        tenant_filter = Filter(
#            must=[
#                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
#            ]
#        )
#        return qdrant_client.search(
#            collection_name="shared_knowledge_graph",
#            query_vector=query_vector,
#            query_filter=tenant_filter,
#            limit=top_k
#        )
