from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str = ""
    phone: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ResendVerificationRequest(BaseModel):
    email: str


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
