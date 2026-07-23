import os
import hashlib
import uuid
from fastapi import UploadFile

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage/documents")


def save_upload_file(upload_file: UploadFile) -> tuple[str, str, int, str]:
    """
    Saves an uploaded file to storage.
    Returns: (stored_filename, storage_path, file_size, checksum)
    """
    os.makedirs(STORAGE_DIR, exist_ok=True)

    # Generate unique stored filename
    file_extension = os.path.splitext(upload_file.filename or "")[1]
    stored_filename = f"{uuid.uuid4()}{file_extension}"
    storage_path = os.path.join(STORAGE_DIR, stored_filename)

    # Write file and calculate checksum (sha256)
    sha256_hasher = hashlib.sha256()
    file_size = 0

    # Ensure seek is at the start
    upload_file.file.seek(0)

    with open(storage_path, "wb") as buffer:
        while file_chunk := upload_file.file.read(8192):
            buffer.write(file_chunk)
            sha256_hasher.update(file_chunk)
            file_size += len(file_chunk)

    checksum = sha256_hasher.hexdigest()
    return stored_filename, storage_path, file_size, checksum


def delete_stored_file(storage_path: str) -> bool:
    """
    Deletes a file from storage if it exists.
    """
    try:
        if os.path.exists(storage_path):
            os.remove(storage_path)
            return True
    except Exception:
        pass
    return False
