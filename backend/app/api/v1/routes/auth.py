from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_storage
from app.core.config import PLAN_LIMITS
from app.core.security import (
    create_access_token,
    create_email_verification_token,
    create_reset_token,
    decode_special_token,
    hash_password,
    verify_password,
)
from app.schemas.auth import (
    AuthTokenResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserPublic,
)
from app.services.storage import StorageManager

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)

# ── In-memory login brute-force protection ─────────────────────────────
_login_failures: dict[str, list[float]] = {}
_LOCKOUT_THRESHOLD = 5
_LOCKOUT_WINDOW = 900  # 15 minutes


def _check_login_lockout(email: str) -> None:
    import time

    now = time.time()
    attempts = _login_failures.get(email, [])
    # Keep only attempts within the window
    attempts = [t for t in attempts if now - t < _LOCKOUT_WINDOW]
    _login_failures[email] = attempts
    if len(attempts) >= _LOCKOUT_THRESHOLD:
        raise HTTPException(
            status_code=403,
            detail="Account locked due to too many failed login attempts. Try again after 15 minutes.",
        )


def _record_login_failure(email: str) -> None:
    import time

    now = time.time()
    attempts = _login_failures.setdefault(email, [])
    attempts.append(now)
    # Prune old
    _login_failures[email] = [t for t in attempts if now - t < _LOCKOUT_WINDOW]


def _clear_login_failures(email: str) -> None:
    _login_failures.pop(email, None)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _to_user_public(user: dict) -> UserPublic:
    return UserPublic(
        user_id=user.get("user_id", ""),
        username=user.get("username", ""),
        email=user.get("email", ""),
        full_name=user.get("full_name", ""),
        phone=user.get("phone", ""),
        subscription_tier=user.get("subscription_tier", "free"),
        email_verified=user.get("email_verified", False),
        plan=user.get("plan", "free"),
        credits=user.get("credits", 0),
        created_at=user.get("created_at", ""),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthTokenResponse)
async def register(
    request: RegisterRequest,
    storage: StorageManager = Depends(get_storage),
) -> AuthTokenResponse:
    email = _normalize_email(request.email)
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Enter a valid email address")

    if await storage.find_user_by_email(email):
        raise HTTPException(status_code=400, detail="Email already exists")

    if await storage.find_user_by_username(request.username):
        raise HTTPException(status_code=400, detail="Username already exists")

    user_data = {
        "username": request.username,
        "email": email,
        "password_hash": hash_password(request.password),
        "full_name": request.full_name,
        "phone": request.phone,
        "subscription_tier": "free",
        "plan": "free",
        "credits": PLAN_LIMITS.get("free", 10),
        "credits_used_this_month": 0,
        "storage_used_bytes": 0,
        "email_verified": False,
        "theme": "dark",
        "preferred_framework": "phaser",
        "ai_provider": "gemini",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    user = await storage.create_user(user_data)

    # Generate email verification token (logged to console in dev)
    verification_token = create_email_verification_token({
        "user_id": user["user_id"],
        "email": email,
    })
    logger.info("Email verification link: /api/v1/auth/verify-email/%s", verification_token)

    token = create_access_token(user["user_id"])
    return AuthTokenResponse(access_token=token, token_type="bearer", user=_to_user_public(user))


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    request: LoginRequest,
    storage: StorageManager = Depends(get_storage),
) -> AuthTokenResponse:
    email = _normalize_email(request.email)

    # Check brute-force lockout
    _check_login_lockout(email)

    user = await storage.find_user_by_email(email)
    if not user or not verify_password(request.password, user.get("password_hash", "")):
        _record_login_failure(email)
        raise HTTPException(status_code=400, detail="Invalid email or password")

    _clear_login_failures(email)
    token = create_access_token(user["user_id"])
    return AuthTokenResponse(access_token=token, token_type="bearer", user=_to_user_public(user))


@router.get("/me", response_model=UserPublic)
async def me(current_user: dict = Depends(get_current_user)) -> UserPublic:
    return _to_user_public(current_user)


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh(current_user: dict = Depends(get_current_user)) -> AuthTokenResponse:
    token = create_access_token(current_user["user_id"])
    return AuthTokenResponse(access_token=token, token_type="bearer", user=_to_user_public(current_user))


@router.post("/logout")
async def logout() -> dict:
    return {"message": "User logged out successfully"}


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    storage: StorageManager = Depends(get_storage),
) -> dict:
    email = _normalize_email(request.email)
    user = await storage.find_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    reset_token = create_reset_token({
        "user_id": user["user_id"],
        "email": user["email"],
    })
    logger.info("Password reset token: %s", reset_token)
    return {"message": "Password reset token generated (check server console)"}


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    storage: StorageManager = Depends(get_storage),
) -> dict:
    try:
        payload = decode_special_token(request.token, "reset")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user_id = payload.get("user_id", "")
    user = await storage.find_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await storage.update_user(user_id, {"password_hash": hash_password(request.new_password)})
    return {"message": "Password reset successfully"}


@router.get("/verify-email/{token}")
async def verify_email(
    token: str,
    storage: StorageManager = Depends(get_storage),
) -> dict:
    try:
        payload = decode_special_token(token, "email_verify")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user_id = payload.get("user_id", "")
    user = await storage.find_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("email_verified"):
        return {"message": "Email already verified"}

    await storage.update_user(user_id, {"email_verified": True})
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
async def resend_verification(
    request: ResendVerificationRequest,
    storage: StorageManager = Depends(get_storage),
) -> dict:
    email = _normalize_email(request.email)
    user = await storage.find_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("email_verified"):
        return {"message": "Email already verified"}

    verification_token = create_email_verification_token({
        "user_id": user["user_id"],
        "email": user["email"],
    })
    logger.info("Resend verification link: /api/v1/auth/verify-email/%s", verification_token)
    return {"message": "Verification email resent"}
