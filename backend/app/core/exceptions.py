from fastapi import HTTPException, status

class EmailAlreadyRegisteredException(HTTPException):
    """Exception raised when registering an email that already exists."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

class IncorrectCredentialsException(HTTPException):
    """Exception raised on invalid login credentials."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

class InactiveUserException(HTTPException):
    """Exception raised when an inactive user attempts to perform operations."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

class CredentialsValidationException(HTTPException):
    """Exception raised when JWT token validation fails."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

class DocumentNotFoundException(HTTPException):
    """Exception raised when a document is not found or user lacks access."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

class ConversationNotFoundException(HTTPException):
    """Exception raised when a conversation session is not found or user lacks access."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

class FileExceedsLimitException(HTTPException):
    """Exception raised when uploaded file exceeds the configured size limit."""
    def __init__(self, limit_mb: float, is_physical: bool = False):
        detail = (
            f"File size physically exceeds the {limit_mb}MB limit."
            if is_physical else
            f"File size exceeds the {limit_mb}MB limit (via Content-Length)."
        )
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=detail
        )

class InvalidFileExtensionException(HTTPException):
    """Exception raised when file extension is not supported."""
    def __init__(self, ext: str, allowed: list[str]):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not allowed. Supported formats: {', '.join(sorted(allowed))}"
        )

class InvalidMimeTypeException(HTTPException):
    """Exception raised when file MIME type is not supported."""
    def __init__(self, mime_type: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME type '{mime_type}' is not allowed. Supported formats: PDF, DOCX, TXT, CSV, XLSX, JSON, Markdown."
        )

class FileStorageSaveException(HTTPException):
    """Exception raised when saving uploaded file to disk fails."""
    def __init__(self, error_msg: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {error_msg}"
        )

class IngestionQueueException(HTTPException):
    """Exception raised when queuing celery ingestion task fails."""
    def __init__(self, error_msg: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue document ingestion: {error_msg}"
        )


class EmptyQuestionException(HTTPException):
    """Exception raised when a user submits an empty chat query."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )


class NoFilesProvidedException(HTTPException):
    """Exception raised when an upload request contains no files."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid file(s) provided in upload request."
        )


class AccessDeniedException(HTTPException):
    """Exception raised when a user tries to access a resource belonging to another tenant."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )


class ExportFileNotFoundException(HTTPException):
    """Exception raised when a requested export file is not found on disk."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found"
        )
