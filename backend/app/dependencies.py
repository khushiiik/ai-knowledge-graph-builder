from typing import Annotated, Generator
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.security import HTTPAuthorizationCredentials
from app.config import settings
from app.core.security import security_scheme, decode_access_token
from app.core.exceptions import CredentialsValidationException, InactiveUserException
from app.models.user import User as UserModel
from app.schemas.user import TokenData

# Configure Database Engine
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Database session lifecycle generator dependency."""
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Session = Depends(get_db),
) -> UserModel:
    """Validate bearer token and retrieve the user from database."""
    decoded_token_payload = decode_access_token(credentials.credentials)
    if decoded_token_payload is None:
        raise CredentialsValidationException()

    email: str | None = decoded_token_payload.get("sub")
    if email is None:
        raise CredentialsValidationException()

    token_data = TokenData(email=email)
    user_by_email = (
        db.query(UserModel).filter(UserModel.email == token_data.email).first()
    )
    if user_by_email is None:
        raise CredentialsValidationException()
    return user_by_email


async def get_current_active_user(
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> UserModel:
    """Ensure the user is active."""
    if not current_user.is_active:
        raise InactiveUserException()
    return current_user
