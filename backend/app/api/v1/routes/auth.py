from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_storage
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.auth import AuthTokenResponse, LoginRequest, RegisterRequest, UserPublic
from app.services.storage import StorageManager

router = APIRouter(prefix="/auth", tags=["auth"])


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
        "theme": "dark",
        "preferred_framework": "phaser",
        "ai_provider": "gemini",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    user = await storage.create_user(user_data)
    token = create_access_token(user["user_id"])
    return AuthTokenResponse(access_token=token, token_type="bearer", user=_to_user_public(user))


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    request: LoginRequest,
    storage: StorageManager = Depends(get_storage),
) -> AuthTokenResponse:
    email = _normalize_email(request.email)
    user = await storage.find_user_by_email(email)
    if not user or not verify_password(request.password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    token = create_access_token(user["user_id"])
    return AuthTokenResponse(access_token=token, token_type="bearer", user=_to_user_public(user))


@router.get("/me", response_model=UserPublic)
async def me(current_user: dict = Depends(get_current_user)) -> UserPublic:
    return _to_user_public(current_user)


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh(current_user: dict = Depends(get_current_user)) -> AuthTokenResponse:
    token = create_access_token(current_user["user_id"])
    return AuthTokenResponse(access_token=token, token_type="bearer", user=_to_user_public(current_user))
