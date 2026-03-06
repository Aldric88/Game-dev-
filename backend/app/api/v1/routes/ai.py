import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user, get_storage
from app.schemas.ai import (
    AIChatRequest,
    AIChatResponse,
    AICodeRequest,
    AICodeResponse,
    AIDesignRequest,
    AIDesignResponse,
    GodotGenerateRequest,
    GodotGenerateResponse,
)
from app.schemas.project import ProjectResponse
from app.services.ai_orchestrator import ai_orchestrator
from app.services.rate_limiter import ai_rate_limiter
from app.services.realtime import RealtimeManager
from app.services.s3_storage import s3_storage
from app.services.storage import StorageManager

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)


def _append_messages(project: dict, user_content: str, assistant_content: str) -> list:
    history = project.get("ai_conversation", [])
    now = datetime.now(timezone.utc).isoformat()
    history.append({"role": "user", "content": user_content, "timestamp": now})
    history.append({"role": "assistant", "content": assistant_content, "timestamp": now})
    return history


def _append_usage_log(project: dict, operation: str, usage: Any) -> list:
    logs = project.get("ai_usage_logs", [])
    logs.append({
        "operation": operation,
        "usage": usage.to_dict() if hasattr(usage, "to_dict") else {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return logs


async def _require_project(project_id: str, storage: StorageManager) -> dict:
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_realtime(request: Request) -> RealtimeManager | None:
    return getattr(request.app.state, "realtime", None)


async def _enforce_rate_limit(user_id: str) -> None:
    result = await ai_rate_limiter.check(user_id)
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {result.retry_after_seconds} seconds.",
        )


@router.post("/design", response_model=AIDesignResponse)
async def generate_design(
    request: AIDesignRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> AIDesignResponse:
    await _enforce_rate_limit(current_user["user_id"])
    project = await _require_project(request.project_id, storage)
    realtime = _get_realtime(req)

    result = await ai_orchestrator.generate_design(
        request.prompt,
        history=project.get("ai_conversation", []),
    )

    history = _append_messages(project, request.prompt, result.summary)
    usage_logs = _append_usage_log(project, "design", result.usage)
    update = {
        "design_doc": result.payload,
        "ai_conversation": history,
        "ai_usage_logs": usage_logs,
        "status": "building",
    }
    updated = await storage.update_project(request.project_id, update)
    await storage.update_user_usage(
        current_user["user_id"], ai_tokens=int(result.usage.total_tokens or 0)
    )

    if realtime:
        await realtime.broadcast(request.project_id, "design_generated", {"summary": result.summary})

    return AIDesignResponse(
        summary=result.summary,
        design_doc=result.payload,
        project=ProjectResponse(**(updated or project)),
    )


@router.post("/generate", response_model=AICodeResponse)
async def generate_code(
    request: AICodeRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> AICodeResponse:
    await _enforce_rate_limit(current_user["user_id"])
    project = await _require_project(request.project_id, storage)
    realtime = _get_realtime(req)

    result = await ai_orchestrator.generate_code(
        request.prompt,
        design_doc=project.get("design_doc"),
        history=project.get("ai_conversation", []),
    )

    files = result.payload.get("files", {})
    framework = request.framework.lower() if request.framework else "phaser"

    # Attempt S3 upload
    if files:
        username = current_user.get("username", "unknown")
        project_name = project.get("name", "untitled")
        try:
            await s3_storage.upload_project_files(username, project_name, files)
        except Exception as e:
            logger.warning("S3 upload failed: %s", e)

    versions = project.get("versions", [])
    versions.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ai-code-generation",
        "files": list(files.keys()),
    })

    history = _append_messages(project, request.prompt, result.summary)
    usage_logs = _append_usage_log(project, "generate", result.usage)
    update = {
        "generated_code": result.payload,
        "ai_conversation": history,
        "ai_usage_logs": usage_logs,
        "versions": versions,
        "status": "building",
    }
    updated = await storage.update_project(request.project_id, update)
    await storage.update_user_usage(
        current_user["user_id"], ai_tokens=int(result.usage.total_tokens or 0)
    )

    if realtime:
        await realtime.broadcast(request.project_id, "code_generated", {"files": list(files.keys())})

    return AICodeResponse(
        generated_code=result.payload,
        project=ProjectResponse(**(updated or project)),
    )


@router.post("/chat", response_model=AIChatResponse)
async def chat(
    request: AIChatRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> AIChatResponse:
    await _enforce_rate_limit(current_user["user_id"])
    project = await _require_project(request.project_id, storage)

    result = await ai_orchestrator.chat_reply(
        request.message,
        project=project,
        history=project.get("ai_conversation", []),
    )
    reply = result.payload.get("reply", "")

    history = _append_messages(project, request.message, reply)
    usage_logs = _append_usage_log(project, "chat", result.usage)
    update = {"ai_conversation": history, "ai_usage_logs": usage_logs}
    updated = await storage.update_project(request.project_id, update)

    realtime = _get_realtime(req)
    if realtime:
        await realtime.broadcast(request.project_id, "chat_message", {"reply": reply})

    return AIChatResponse(reply=reply, project=ProjectResponse(**(updated or project)))


@router.post("/godot/generate", response_model=GodotGenerateResponse)
async def generate_godot_game(
    request: GodotGenerateRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> GodotGenerateResponse:
    await _enforce_rate_limit(current_user["user_id"])
    project = await _require_project(request.project_id, storage)
    realtime = _get_realtime(req)

    username = current_user.get("username", "unknown")
    project_name = project.get("name", "untitled")

    result = await ai_orchestrator.generate_complete_game(
        prompt=request.prompt,
        username=username,
        project_name=project_name,
        project_id=request.project_id,
        realtime=realtime,
    )

    update = {
        "design_doc": result.design_doc,
        "status": result.status,
    }
    await storage.update_project(request.project_id, update)

    return GodotGenerateResponse(
        status=result.status,
        design_doc=result.design_doc,
        file_urls=result.file_urls,
        stats=result.stats,
        errors=result.errors,
    )
