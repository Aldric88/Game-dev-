from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_reset_token(data: dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload = {**data, "exp": expire, "type": "reset"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_email_verification_token(data: dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {**data, "exp": expire, "type": "email_verify"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except (JWTError, ValueError):
        raise ValueError("Invalid or expired token")


def decode_special_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode a reset or email verification token, validating the type claim."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except (JWTError, ValueError):
        raise ValueError("Invalid or expired token")
    if payload.get("type") != expected_type:
        raise ValueError("Invalid token type")
    return payload
