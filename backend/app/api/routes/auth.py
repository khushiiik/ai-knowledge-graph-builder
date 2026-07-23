from datetime import timedelta
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    blacklist_token,
    is_token_blacklisted,
)
from app.core.exceptions import (
    EmailAlreadyRegisteredException,
    IncorrectCredentialsException,
    InactiveUserException,
    CredentialsValidationException,
)
from app.dependencies import get_db
from app.models.user import User as UserModel
from app.schemas.user import UserCreate, UserRead, Token, UserLogin, RefreshTokenRequest

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user_create: UserCreate, db: Session = Depends(get_db)):
    """Register a new user dynamically."""
    # Check if email already exists
    existing_user = (
        db.query(UserModel).filter(UserModel.email == user_create.email).first()
    )
    if existing_user:
        raise EmailAlreadyRegisteredException()

    hashed_password = get_password_hash(user_create.password)
    new_user = UserModel(
        email=user_create.email,
        full_name=user_create.full_name,
        hashed_password=hashed_password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/token", response_model=Token)
def login_for_access_token(
    login_credentials: UserLogin, db: Session = Depends(get_db)
) -> Token:
    """Authenticate credentials dynamically and return an access token and a refresh token."""
    authenticated_user = (
        db.query(UserModel).filter(UserModel.email == login_credentials.email).first()
    )
    if not authenticated_user or not verify_password(
        login_credentials.password, authenticated_user.hashed_password
    ):
        raise IncorrectCredentialsException()
    if not authenticated_user.is_active:
        raise InactiveUserException()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": authenticated_user.email}, expires_delta=access_token_expires
    )
    refresh_token_string = create_refresh_token(data={"sub": authenticated_user.email})
    return Token(
        access_token=access_token,
        refresh_token=refresh_token_string,
        token_type="bearer",
    )


@router.post("/refresh", response_model=Token)
def refresh_token(
    refresh_request_payload: Optional[RefreshTokenRequest] = None,
    authorization_credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db),
) -> Token:
    """Issue a new access token using a valid refresh token."""
    refresh_token_string = None
    if refresh_request_payload and refresh_request_payload.refresh_token:
        refresh_token_string = refresh_request_payload.refresh_token
    elif authorization_credentials and authorization_credentials.credentials:
        refresh_token_string = authorization_credentials.credentials

    if not refresh_token_string or is_token_blacklisted(refresh_token_string):
        raise CredentialsValidationException()

    decoded_token_payload = decode_access_token(refresh_token_string)
    if not decoded_token_payload or decoded_token_payload.get("type") != "refresh":
        raise CredentialsValidationException()

    email: Optional[str] = decoded_token_payload.get("sub")
    if not email:
        raise CredentialsValidationException()

    associated_user = db.query(UserModel).filter(UserModel.email == email).first()
    if not associated_user:
        raise CredentialsValidationException()
    if not associated_user.is_active:
        raise InactiveUserException()

    # Blacklist the old refresh token as part of refresh token rotation
    blacklist_token(refresh_token_string)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = create_access_token(
        data={"sub": associated_user.email}, expires_delta=access_token_expires
    )
    new_refresh_token = create_refresh_token(data={"sub": associated_user.email})
    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    refresh_request_payload: Optional[RefreshTokenRequest] = None,
    authorization_credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
):
    """Invalidate current access and refresh tokens."""
    if authorization_credentials and authorization_credentials.credentials:
        blacklist_token(authorization_credentials.credentials)
    if refresh_request_payload and refresh_request_payload.refresh_token:
        blacklist_token(refresh_request_payload.refresh_token)
    return {"message": "Logged out successfully. Tokens invalidated."}
