from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, status

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.exceptions import (
    EmailAlreadyRegisteredException,
    IncorrectCredentialsException,
    InactiveUserException
)
from app.dependencies import get_db, get_current_active_user
from app.models.user import User as UserModel
from app.schemas.user import UserCreate, UserRead, Token, UserLogin

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
    """Authenticate credentials dynamically and return an access token."""
    user = db.query(UserModel).filter(UserModel.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise IncorrectCredentialsException()
    if not user.is_active:
        raise InactiveUserException()
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")

@router.post("/refresh", response_model=Token)
def refresh_token(
    current_user: Annotated[UserModel, Depends(get_current_active_user)]
) -> Token:
    """Issue a new access token for the currently authenticated active user."""
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": current_user.email}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")
