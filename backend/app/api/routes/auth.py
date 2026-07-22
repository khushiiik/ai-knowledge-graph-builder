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
    is_token_blacklisted
)
from app.core.exceptions import (
    EmailAlreadyRegisteredException,
    IncorrectCredentialsException,
    InactiveUserException,
    CredentialsValidationException
)
from app.dependencies import get_db
from app.models.user import User as UserModel
from app.schemas.user import UserCreate, UserRead, Token, UserLogin, RefreshTokenRequest

router = APIRouter(prefix="/auth", tags=["authentication"])

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Register a new user dynamically."""
    # Check if email already exists
    db_user = db.query(UserModel).filter(UserModel.email == user_in.email).first()
    if db_user:
        raise EmailAlreadyRegisteredException()
    
    hashed_password = get_password_hash(user_in.password)
    new_user = UserModel(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hashed_password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/token", response_model=Token)
def login_for_access_token(
    login_data: UserLogin,
    db: Session = Depends(get_db)
) -> Token:
    """Authenticate credentials dynamically and return an access token and a refresh token."""
    user = db.query(UserModel).filter(UserModel.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise IncorrectCredentialsException()
    if not user.is_active:
        raise InactiveUserException()
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    refresh_token_str = create_refresh_token(
        data={"sub": user.email}
    )
    return Token(access_token=access_token, refresh_token=refresh_token_str, token_type="bearer")

@router.post("/refresh", response_model=Token)
def refresh_token(
    refresh_data: Optional[RefreshTokenRequest] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
) -> Token:
    """Issue a new access token using a valid refresh token."""
    token_str = None
    if refresh_data and refresh_data.refresh_token:
        token_str = refresh_data.refresh_token
    elif credentials and credentials.credentials:
        token_str = credentials.credentials

    if not token_str or is_token_blacklisted(token_str):
        raise CredentialsValidationException()

    payload = decode_access_token(token_str)
    if not payload or payload.get("type") != "refresh":
        raise CredentialsValidationException()

    email: str | None = payload.get("sub")
    if not email:
        raise CredentialsValidationException()

    user = db.query(UserModel).filter(UserModel.email == email).first()
    if not user:
        raise CredentialsValidationException()
    if not user.is_active:
        raise InactiveUserException()

    # Blacklist the old refresh token as part of refresh token rotation
    blacklist_token(token_str)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    new_refresh_token = create_refresh_token(
        data={"sub": user.email}
    )
    return Token(access_token=new_access_token, refresh_token=new_refresh_token, token_type="bearer")

@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    refresh_data: Optional[RefreshTokenRequest] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
):
    """Invalidate current access and refresh tokens."""
    if credentials and credentials.credentials:
        blacklist_token(credentials.credentials)
    if refresh_data and refresh_data.refresh_token:
        blacklist_token(refresh_data.refresh_token)
    return {"message": "Logged out successfully. Tokens invalidated."}
