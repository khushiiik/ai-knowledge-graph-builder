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
    file_ext = os.path.splitext(upload_file.filename or "")[1]
    stored_filename = f"{uuid.uuid4()}{file_ext}"
    storage_path = os.path.join(STORAGE_DIR, stored_filename)
    
    # Write file and calculate checksum (sha256)
    sha256 = hashlib.sha256()
    file_size = 0
    
    # Ensure seek is at the start
    upload_file.file.seek(0)
    
    with open(storage_path, "wb") as buffer:
        while chunk := upload_file.file.read(8192):
            buffer.write(chunk)
            sha256.update(chunk)
            file_size += len(chunk)
            
    checksum = sha256.hexdigest()
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
