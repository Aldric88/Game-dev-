from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_access_token
from app.services.storage import StorageManager

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_storage(request: Request) -> StorageManager:
    return request.app.state.storage


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    storage: StorageManager = Depends(get_storage),
) -> dict:
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub", "")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await storage.find_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_optional(
    request: Request,
    storage: StorageManager = Depends(get_storage),
) -> dict | None:
    """Optional authentication - returns None if not authenticated instead of raising an exception."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[-1]
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub", "")
        return await storage.find_user_by_id(user_id)
    except Exception:
        return None
