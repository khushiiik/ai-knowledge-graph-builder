import pytest
import jwt
from datetime import timedelta
from fastapi import status
from app.core.security import get_password_hash, create_refresh_token, decode_access_token
from app.dependencies import get_current_user, get_current_active_user
from app.models.user import User as UserModel
from app.config import settings

def test_registration_success(client, db_session):
    # Register endpoint tests
    payload = {
        "email": "newuser@example.com",
        "full_name": "New User",
        "password": "strongpassword123"
    }
    res = client.post("/auth/register", json=payload)
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert "id" in data

def test_login_success(client, db_session):
    # Disable dependency override to test real auth login check against SQLite
    client.app.dependency_overrides.pop(get_current_user, None)
    client.app.dependency_overrides.pop(get_current_active_user, None)

    # Seed user in DB
    hashed = get_password_hash("password123")
    user = UserModel(
        email="loginuser@example.com",
        full_name="Login User",
        hashed_password=hashed,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    payload = {
        "email": "loginuser@example.com",
        "password": "password123"
    }
    res = client.post("/auth/token", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

def test_refresh_token_success(client, db_session):
    client.app.dependency_overrides.pop(get_current_user, None)
    client.app.dependency_overrides.pop(get_current_active_user, None)

    # Seed user in DB
    hashed = get_password_hash("password123")
    user = UserModel(
        email="refreshuser@example.com",
        full_name="Refresh User",
        hashed_password=hashed,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    # Generate real refresh token
    ref_token = create_refresh_token(data={"sub": "refreshuser@example.com"})

    res = client.post("/auth/refresh", json={"refresh_token": ref_token})
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data

def test_invalid_refresh_token(client, db_session):
    # Pass an access token to /refresh instead of a refresh token
    import app.core.security as sec
    bad_token = sec.create_access_token(data={"sub": "user@example.com"})
    res = client.post("/auth/refresh", json={"refresh_token": bad_token})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED

def test_expired_refresh_token(client, db_session):
    client.app.dependency_overrides.pop(get_current_user, None)
    client.app.dependency_overrides.pop(get_current_active_user, None)

    # Seed user in DB
    hashed = get_password_hash("password123")
    user = UserModel(
        email="expireduser@example.com",
        full_name="Expired User",
        hashed_password=hashed,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    # Create expired refresh token using negative expiry delta
    expired_token = create_refresh_token(
        data={"sub": "expireduser@example.com"},
        expires_delta=timedelta(seconds=-10)
    )

    res = client.post("/auth/refresh", json={"refresh_token": expired_token})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
