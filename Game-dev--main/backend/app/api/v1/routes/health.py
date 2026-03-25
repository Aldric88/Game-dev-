from fastapi import APIRouter, Request

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health(request: Request) -> dict:
    storage = request.app.state.storage
    return {
        "service": "game-ai-platform-api",
        "version": "0.1.0",
        "storage": {"mode": storage.mode},
    }
