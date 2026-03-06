from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from auth_service.database import users_collection
from auth_service.utils.auth_dependency import get_current_user
from auth_service.config.plans import PLAN_LIMITS

router = APIRouter()

@router.get("/users/me")
async def get_profile(current_user = Depends(get_current_user)):

    user = await users_collection.find_one(
        {"_id": ObjectId(current_user["user_id"])}
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "email": user["email"],
        "username": user["username"],
        "plan": user["plan"],
        "credits": user["credits"],
        "email_verified": user["email_verified"]
    }

@router.patch("/users/me")
async def update_profile(
    username: str,
    current_user = Depends(get_current_user)
):

    await users_collection.update_one(
        {"_id": ObjectId(current_user["user_id"])},
        {"$set": {"username": username}}
    )

    return {"message": "Profile updated successfully"}

@router.get("/users/me/usage")
async def get_usage(current_user = Depends(get_current_user)):

    user = await users_collection.find_one(
        {"_id": ObjectId(current_user["user_id"])}
    )

    return {
        "plan": user["plan"],
        "credits": user["credits"],
        "credits_used_this_month": user.get("credits_used_this_month", 0),
        "storage_used_bytes": user.get("storage_used_bytes", 0)
    }

@router.delete("/users/me")
async def delete_account(current_user = Depends(get_current_user)):

    await users_collection.delete_one(
        {"_id": ObjectId(current_user["user_id"])}
    )

    return {"message": "Account deleted successfully"}

@router.get("/users/me/credits")
async def get_credits(current_user=Depends(get_current_user)):

    user = await users_collection.find_one(
        {"_id": ObjectId(current_user["user_id"])}
    )

    plan_limit = PLAN_LIMITS.get(user["plan"], 10)

    return {
        "plan": user["plan"],
        "credits_remaining": user["credits"],
        "credits_limit": plan_limit,
        "credits_used_this_month": user["credits_used_this_month"]
    }

@router.post("/users/me/deduct-credit")
async def deduct_credit(current_user=Depends(get_current_user)):

    user_id = current_user["user_id"]

    result = await users_collection.update_one(
        {
            "_id": ObjectId(user_id),
            "credits": {"$gt": 0}   # ensure credits > 0
        },
        {
            "$inc": {
                "credits": -1,
                "credits_used_this_month": 1
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=402,
            detail="No credits remaining"
        )

    return {"message": "Credit deducted successfully"}

@router.post("/users/me/add-credits")
async def add_credits(amount: int, current_user=Depends(get_current_user)):

    user_id = current_user["user_id"]

    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$inc": {"credits": amount}}
    )

    return {
        "message": f"{amount} credits added successfully"
    }
