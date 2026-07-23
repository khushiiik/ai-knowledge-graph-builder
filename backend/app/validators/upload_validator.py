import os
from fastapi import UploadFile, Request
from app.core.exceptions import (
    FileExceedsLimitException,
    InvalidFileExtensionException,
    InvalidMimeTypeException,
)

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
                content_length_bytes = int(content_length)
                if content_length_bytes > MAX_FILE_SIZE_BYTES:
                    raise FileExceedsLimitException(
                        limit_mb=MAX_FILE_SIZE_MB - 1, is_physical=False
                    )
            except ValueError:
                pass

    # 2. Extension validation
    filename = file.filename or ""
    file_extension = os.path.splitext(filename.lower())[1]
    if file_extension not in ALLOWED_EXTENSIONS:
        raise InvalidFileExtensionException(
            ext=file_extension, allowed=list(ALLOWED_EXTENSIONS)
        )

    # 3. MIME type validation
    mime_type = file.content_type
    if not mime_type or mime_type not in ALLOWED_MIME_TYPES:
        raise InvalidMimeTypeException(mime_type=mime_type)

    # 4. Chunk validation (Safety check against fake/altered Content-Length headers)
    # Stream the file to ensure memory consumption stays extremely low
    file.file.seek(0)
    total_size_bytes = 0
    chunk_size_bytes = 1024 * 1024  # 1MB chunks

    while file_chunk := file.file.read(chunk_size_bytes):
        total_size_bytes += len(file_chunk)
        if total_size_bytes > MAX_FILE_SIZE_BYTES:
            raise FileExceedsLimitException(limit_mb=MAX_FILE_SIZE_MB, is_physical=True)

    # Reset seek pointer for next operations
    file.file.seek(0)
