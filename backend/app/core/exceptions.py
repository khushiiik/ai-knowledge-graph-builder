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
