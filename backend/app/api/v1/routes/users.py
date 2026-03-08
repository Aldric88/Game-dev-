from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_storage
from app.core.config import PLAN_LIMITS
from app.schemas.auth import UserPublic, UserUpdateRequest, UserUsageResponse
from app.services.storage import StorageManager

router = APIRouter(prefix="/users", tags=["users"])


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


@router.get("/me", response_model=UserPublic)
async def get_profile(current_user: dict = Depends(get_current_user)) -> UserPublic:
    return _to_user_public(current_user)


@router.patch("/me", response_model=UserPublic)
async def update_profile(
    request: UserUpdateRequest,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> UserPublic:
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No update payload provided")

    updated = await storage.update_user(current_user["user_id"], update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_user_public(updated)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> None:
    await storage.delete_user(current_user["user_id"])


@router.get("/me/usage", response_model=UserUsageResponse)
async def get_usage(current_user: dict = Depends(get_current_user)) -> UserUsageResponse:
    plan = current_user.get("plan", "free")
    return UserUsageResponse(
        plan=plan,
        credits=current_user.get("credits", 0),
        credits_used_this_month=current_user.get("credits_used_this_month", 0),
        credits_limit=PLAN_LIMITS.get(plan, 10),
        storage_used_bytes=current_user.get("storage_used_bytes", 0),
    )


@router.get("/me/credits")
async def get_credits(current_user: dict = Depends(get_current_user)) -> dict:
    plan = current_user.get("plan", "free")
    return {
        "plan": plan,
        "credits_remaining": current_user.get("credits", 0),
        "credits_limit": PLAN_LIMITS.get(plan, 10),
        "credits_used_this_month": current_user.get("credits_used_this_month", 0),
    }


@router.post("/me/deduct-credit")
async def deduct_credit(
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> dict:
    success = await storage.deduct_credit(current_user["user_id"])
    if not success:
        raise HTTPException(status_code=402, detail="No credits remaining")
    return {"message": "Credit deducted successfully"}


@router.post("/me/add-credits")
async def add_credits(
    amount: int,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    await storage.add_credits(current_user["user_id"], amount)
    return {"message": f"{amount} credits added successfully"}
