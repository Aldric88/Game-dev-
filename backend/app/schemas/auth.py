from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str = ""
    phone: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    user_id: str = ""
    username: str = ""
    email: str = ""
    full_name: str = ""
    phone: str = ""
    subscription_tier: str = "free"
    created_at: str = ""


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
