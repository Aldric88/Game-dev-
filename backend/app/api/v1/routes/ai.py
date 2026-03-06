import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, JSONResponse

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
from app.services.local_storage import save_project_files, zip_project, zip_project_from_files, open_project_folder, launch_godot
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
        realtime=realtime,
        project_id=request.project_id,
    )

    files = result.payload.get("files", {})
    framework = request.framework.lower() if request.framework else "phaser"

    # Save files locally to /generatedprojects
    if files:
        project_name = project.get("name", "untitled")
        try:
            saved_dir = save_project_files(project_name, request.project_id, files)
            logger.info("Local save: %s", saved_dir)
        except Exception as e:
            logger.warning("Local save failed: %s", e)

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
        "source": "ai-multi-agent-generation",
        "files": list(files.keys()),
        "agents": ["design", "script", "scene", "asset", "assembler"],
    })

    history = _append_messages(project, request.prompt, result.summary)
    usage_logs = _append_usage_log(project, "generate", result.usage)

    # Store design doc from pipeline if available
    new_design = result.payload.get("design_doc") or project.get("design_doc", {})

    update = {
        "generated_code": result.payload,
        "design_doc": new_design,
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
        await realtime.broadcast(request.project_id, "code_generated", {
            "files": list(files.keys()),
            "agents_used": ["design", "script", "scene", "asset", "assembler"],
            "godot_stats": result.payload.get("godot_stats", {}),
        })

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


@router.get("/download/{project_id}")
async def download_project_zip(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Download all generated project files as a ZIP archive."""
    project = await _require_project(project_id, storage)
    generated_code = project.get("generated_code", {})
    files = generated_code.get("files", {})
    if not files:
        raise HTTPException(status_code=404, detail="No generated files to download")

    project_name = project.get("name", "untitled")
    zip_bytes = zip_project_from_files(project_name, files)

    safe_name = "".join(c if (c.isalnum() or c in " _-") else "_" for c in project_name).strip() or "project"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )

@router.post("/open-folder/{project_id}")
async def open_folder(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Open the generated project folder in the system file explorer."""
    project = await _require_project(project_id, storage)
    project_name = project.get("name", "untitled")
    result = open_project_folder(project_name, project_id)
    status = 200 if result["success"] else 404
    return JSONResponse(content=result, status_code=status)


@router.post("/run-godot/{project_id}")
async def run_godot(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Launch Godot editor with the generated project."""
    project = await _require_project(project_id, storage)
    project_name = project.get("name", "untitled")
    result = launch_godot(project_name, project_id)
    status = 200 if result["success"] else 404
    return JSONResponse(content=result, status_code=status)