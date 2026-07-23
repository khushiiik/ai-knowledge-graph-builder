from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from fastapi.security import HTTPBearer
from app.config import settings

# Initialize password hashing
password_hash = PasswordHash.recommended()

# HTTP Bearer scheme for token extraction
security_scheme = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return password_hash.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token."""
    claims_to_encode = data.copy()
    if expires_delta:
        expiration_time = datetime.now(timezone.utc) + expires_delta
    else:
        expiration_time = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    claims_to_encode.update({"exp": expiration_time, "type": "access"})
    encoded_json_web_token = jwt.encode(
        claims_to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_json_web_token


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT refresh token."""
    claims_to_encode = data.copy()
    if expires_delta:
        expiration_time = datetime.now(timezone.utc) + expires_delta
    else:
        expiration_time = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    claims_to_encode.update({"exp": expiration_time, "type": "refresh"})
    encoded_json_web_token = jwt.encode(
        claims_to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_json_web_token


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT access token. Returns the payload or None if invalid or blacklisted."""
    if is_token_blacklisted(token):
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except InvalidTokenError:
        return None


# Token Blacklist Mechanism
_in_memory_blacklist: set[str] = set()


def blacklist_token(token: str) -> None:
    """Invalidates a JWT token by adding it to the blacklist."""
    if not token:
        return
    _in_memory_blacklist.add(token)
    try:
        import redis

        redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        redis_client.setex(f"blacklist:{token}", 604800, "1")  # Expire after 7 days
    except Exception:
        pass


def is_token_blacklisted(token: str) -> bool:
    """Checks if a JWT token has been invalidated."""
    if not token:
        return False
    if token in _in_memory_blacklist:
        return True
    try:
        import redis

        redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        if redis_client.get(f"blacklist:{token}"):
            return True
    except Exception:
        pass
    return False
