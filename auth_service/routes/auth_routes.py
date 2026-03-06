from bson import ObjectId
from fastapi import APIRouter, HTTPException
from auth_service.database import users_collection
from auth_service.schemas.user_schema import UserRegister
from auth_service.utils.password import hash_password

from auth_service.schemas.login_schema import UserLogin

from auth_service.schemas.login_schema import ForgotPassword, ResetPassword
from auth_service.utils.jwt_handler import create_access_token, create_refresh_token
from auth_service.utils.password import verify_password
from auth_service.utils.jwt_handler import create_reset_token
from auth_service.utils.jwt_handler import create_email_verification_token
from auth_service.utils.redis_client import redis_client

router = APIRouter()

@router.post("/auth/register")
async def register(user: UserRegister):

    # check if email already exists
    existing_user = await users_collection.find_one({"email": user.email})

    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # hash password
    hashed_password = hash_password(user.password)

    user_data = {
    "email": user.email,
    "username": user.username,
    "password": hashed_password,
    "plan": "free",
    "credits": 10,
    "credits_used_this_month": 0,
    "storage_used_bytes": 0,
    "email_verified": False
     }

    result = await users_collection.insert_one(user_data)

    verification_token = create_email_verification_token({
    "user_id": str(result.inserted_id),
    "email": user.email
})
    
    print("EMAIL VERIFICATION LINK:")
    print(f"http://127.0.0.1:8001/auth/verify-email/{verification_token}")

    return {
    "message": "User registered successfully. Verify email."
}

@router.post("/auth/login")
async def login(user: UserLogin):

    db_user = await users_collection.find_one({"email": user.email})

    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    lock_key = f"lock:{user.email}"
    fail_key = f"fail:{user.email}"

    # Check if account locked
    if redis_client.exists(lock_key):
        raise HTTPException(
            status_code=403,
            detail="Account locked. Try again after 15 minutes."
        )

    # Check password
    if not verify_password(user.password, db_user["password"]):

        attempts = redis_client.incr(fail_key)

        if attempts == 1:
            redis_client.expire(fail_key, 900)  # 15 minutes

        if attempts >= 5:

            redis_client.set(lock_key, "locked", ex=900)

            raise HTTPException(
                status_code=403,
                detail="Account locked due to too many failed login attempts"
            )

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Reset counter on success
    redis_client.delete(fail_key)

    token_data = {
        "user_id": str(db_user["_id"]),
        "email": db_user["email"]
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

from jose import jwt, JWTError
from auth_service.utils.jwt_handler import SECRET_KEY, ALGORITHM


@router.post("/auth/refresh")
async def refresh_token(refresh_token: str):

    try:

        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])

        new_access_token = create_access_token({
            "user_id": payload["user_id"],
            "email": payload["email"]
        })

        return {
            "access_token": new_access_token
        }

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
@router.post("/auth/logout")
async def logout():

    return {
        "message": "User logged out successfully"
    }

@router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPassword):

    user = await users_collection.find_one({"email": data.email})

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    reset_token = create_reset_token({
        "user_id": str(user["_id"]),
        "email": user["email"]
    })

    # simulate email
    print("RESET TOKEN:", reset_token)

    return {
        "message": "Password reset token generated (check server console)"
    }

@router.post("/auth/reset-password")
async def reset_password(data: ResetPassword):

    try:

        payload = jwt.decode(data.token, SECRET_KEY, algorithms=[ALGORITHM])

        user_id = payload["user_id"]

        hashed_password = hash_password(data.new_password)

        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"password": hashed_password}}
        )

        return {
            "message": "Password reset successfully"
        }

    except JWTError:

        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
@router.get("/auth/verify-email/{token}")
async def verify_email(token: str):

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        user_id = payload["user_id"]

        user = await users_collection.find_one({"_id": ObjectId(user_id)})

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # already verified
        if user.get("email_verified"):
            return {"message": "Email already verified"}

        await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"email_verified": True}}
        )

        return {"message": "Email verified successfully"}

    except JWTError:

        raise HTTPException(status_code=400, detail="Invalid or expired token")
    

@router.post("/auth/resend-verification")
async def resend_verification(email: str):

    user = await users_collection.find_one({"email": email})

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("email_verified"):
        return {"message": "Email already verified"}

    verification_token = create_email_verification_token({
        "user_id": str(user["_id"]),
        "email": user["email"]
    })

    print("NEW VERIFICATION LINK:")
    print(f"http://127.0.0.1:8001/auth/verify-email/{verification_token}")

    return {"message": "Verification email resent"}