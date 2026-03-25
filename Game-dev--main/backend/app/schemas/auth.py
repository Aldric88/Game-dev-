from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, pattern=r'^[a-zA-Z0-9_]+$')
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=20)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class UserPublic(BaseModel):
    user_id: str = ""
    username: str = ""
    email: str = ""
    full_name: str = ""
    phone: str = ""
    subscription_tier: str = "free"
    email_verified: bool = False
    plan: str = "free"
    credits: int = 0
    created_at: str = ""

    @classmethod
    def from_db(cls, user: dict) -> "UserPublic":
        """Build a UserPublic from a raw storage dict."""
        return cls(
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


class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None


class UserUsageResponse(BaseModel):
    plan: str = "free"
    credits: int = 0
    credits_used_this_month: int = 0
    credits_limit: int = 10
    storage_used_bytes: int = 0


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
