import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, JSONResponse, StreamingResponse
from pydantic import BaseModel

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
from app.services.ml_feedback import record_game_creation
from app.services.mapl_service import mapl_service
from app.schemas.mapl import MemoryAction, MemoryState, Outcome
from app.ml.prompt_scorer import score_prompt
from app.ml.success_predictor import predict_success
from app.services.rate_limiter import ai_rate_limiter
from app.services.realtime import RealtimeManager
from app.services.s3_storage import s3_storage
from app.services.storage import StorageManager

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)

_MAX_VERSIONS = 20
_MAX_CONVERSATION = 100  # individual message entries (= 50 user+assistant pairs)


def _append_messages(
    project: dict,
    user_content: str,
    assistant_content: str,
    user_sent_at: str | None = None,
) -> list:
    """Append a user+assistant message pair with distinct timestamps.

    ``user_sent_at`` should be the ISO timestamp recorded *before* the AI call
    so the user message reflects when the request was made, not when it returned.
    """
    history = list(project.get("ai_conversation", []))
    user_ts = user_sent_at or datetime.now(timezone.utc).isoformat()
    assistant_ts = datetime.now(timezone.utc).isoformat()
    history.append({"role": "user", "content": user_content, "timestamp": user_ts})
    history.append({"role": "assistant", "content": assistant_content, "timestamp": assistant_ts})
    # Keep only the most recent entries (50 pairs) to prevent unbounded growth.
    return history[-_MAX_CONVERSATION:]


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


async def _require_owned_project(project_id: str, storage: StorageManager, current_user: dict) -> dict:
    project = await _require_project(project_id, storage)
    if project.get("user_id") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return project


def _get_realtime(request: Request) -> RealtimeManager | None:
    return getattr(request.app.state, "realtime", None)


_ERROR_KEYWORDS = frozenset([
    "error", "bug", "broken", "crash", "fix", "doesn't work", "not working",
    "failed", "exception", "undefined", "null", "issue", "wrong", "incorrect",
    "problem", "mistake", "fail", "glitch", "weird",
])


def _detect_error_signal(message: str) -> bool:
    """Return True if the user message suggests they are reporting an error."""
    low = message.lower()
    return any(kw in low for kw in _ERROR_KEYWORDS)


async def _record_chat_mapl_memory(
    storage: StorageManager,
    user_id: str,
    message: str,
    project: dict,
    reward: float,
    outcome: Outcome,
) -> None:
    """Fire-and-forget: record a chat interaction as a user-specific MAPL memory."""
    try:
        design_doc = project.get("design_doc") or {}
        state = MemoryState(
            prompt=message,
            game_type=design_doc.get("game_type", ""),
            entity_count=len(design_doc.get("entities", [])),
            context_features={"error_message": message[:200]},
        )
        action = MemoryAction(action_type="chat", temperature=0.7)
        await mapl_service.store_memory(
            state=state,
            action=action,
            reward=reward,
            outcome=outcome,
            user_id=user_id,
            storage=storage,
        )
    except Exception as exc:
        logger.warning("MAPL chat memory recording failed: %s", exc)


async def _record_mapl_memory(
    storage: StorageManager,
    prompt: str,
    design_doc: dict,
    reward: float,
    outcome: Outcome,
    user_id: str,
) -> None:
    """Fire-and-forget helper to record a MAPL experience memory."""
    try:
        game_type = design_doc.get("game_type", "")
        entities = design_doc.get("entities", [])
        mechanics = design_doc.get("mechanics", [])

        state = MemoryState(
            prompt=prompt,
            game_type=game_type,
            entity_count=len(entities),
            context_features={
                "mechanics": mechanics,
                "visual_style": design_doc.get("visual_style", {}),
            },
        )
        action = MemoryAction(action_type="generate", temperature=0.7)
        await mapl_service.store_memory(
            state=state,
            action=action,
            reward=reward,
            outcome=outcome,
            user_id=user_id,
            storage=storage,
        )
    except Exception as exc:
        logger.warning("MAPL memory recording failed: %s", exc)


async def _enforce_rate_limit(user_id: str) -> None:
    result = await ai_rate_limiter.check(user_id)
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {result.retry_after_seconds} seconds.",
        )


async def _enforce_credits(user_id: str, storage: StorageManager) -> None:
    """Deduct one credit atomically. Raises 402 if the user has none left."""
    success = await storage.deduct_credit(user_id)
    if not success:
        raise HTTPException(
            status_code=402,
            detail="No credits remaining. Please wait for your monthly reset or upgrade your plan.",
        )


@router.post("/design", response_model=AIDesignResponse)
async def generate_design(
    request: AIDesignRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> AIDesignResponse:
    await _enforce_rate_limit(current_user["user_id"])
    await _enforce_credits(current_user["user_id"], storage)
    project = await _require_owned_project(request.project_id, storage, current_user)
    realtime = _get_realtime(req)

    user_sent_at = datetime.now(timezone.utc).isoformat()
    result = await ai_orchestrator.generate_design(
        request.prompt,
        history=project.get("ai_conversation", []),
        storage=storage,
        user_id=current_user["user_id"],
    )

    history = _append_messages(project, request.prompt, result.summary, user_sent_at)
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

    # Capture ML training signal — fire-and-forget
    game_type = result.payload.get("game_type") if result.payload else None
    if game_type and request.prompt:
        asyncio.create_task(record_game_creation(
            storage=storage,
            prompt=request.prompt,
            game_type=game_type,
            confidence=1.0,   # AI-confirmed game type = fully trusted signal
        ))

    prompt_score       = score_prompt(request.prompt)
    success_prediction = predict_success(result.payload) if result.payload else {}

    return AIDesignResponse(
        summary=result.summary,
        design_doc=result.payload,
        project=ProjectResponse(**(updated or project)),
        prompt_score=prompt_score,
        success_prediction=success_prediction,
    )


@router.post("/generate", response_model=AICodeResponse)
async def generate_code(
    request: AICodeRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> AICodeResponse:
    await _enforce_rate_limit(current_user["user_id"])
    await _enforce_credits(current_user["user_id"], storage)
    project = await _require_owned_project(request.project_id, storage, current_user)
    realtime = _get_realtime(req)

    user_sent_at = datetime.now(timezone.utc).isoformat()
    result = await ai_orchestrator.generate_code(
        request.prompt,
        design_doc=project.get("design_doc"),
        history=project.get("ai_conversation", []),
        realtime=realtime,
        project_id=request.project_id,
    )

    files = result.payload.get("files", {})

    # Save files locally to /generatedprojects (run in thread — disk I/O is blocking)
    if files:
        project_name = project.get("name", "untitled")
        try:
            saved_dir = await asyncio.to_thread(save_project_files, project_name, request.project_id, files)
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
    versions = versions[-_MAX_VERSIONS:]

    history = _append_messages(project, request.prompt, result.summary, user_sent_at)
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

    # ── MAPL: Record successful generation as experience memory ──────────
    agent_errors = result.payload.get("agent_errors", [])
    mapl_reward = 1.0 if not agent_errors else max(0.3, 1.0 - 0.1 * len(agent_errors))
    mapl_outcome = Outcome.SUCCESS if not agent_errors else Outcome.PARTIAL
    asyncio.create_task(_record_mapl_memory(
        storage=storage,
        prompt=request.prompt,
        design_doc=new_design,
        reward=mapl_reward,
        outcome=mapl_outcome,
        user_id=current_user["user_id"],
    ))

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
    await _enforce_credits(current_user["user_id"], storage)
    project = await _require_owned_project(request.project_id, storage, current_user)
    user_id = current_user["user_id"]

    user_sent_at = datetime.now(timezone.utc).isoformat()
    result = await ai_orchestrator.chat_reply(
        request.message,
        project=project,
        history=project.get("ai_conversation", []),
        user_id=user_id,
        storage=storage,
    )
    reply = result.payload.get("reply", "")
    file_changes: dict = result.payload.get("file_changes", {})

    history = _append_messages(project, request.message, reply, user_sent_at)
    usage_logs = _append_usage_log(project, "chat", result.usage)
    update: dict = {"ai_conversation": history, "ai_usage_logs": usage_logs}

    # Apply any file changes the AI produced directly into the project
    if file_changes:
        existing_code = dict(project.get("generated_code") or {})
        existing_files = dict(existing_code.get("files", {}))
        existing_files.update(file_changes)
        existing_code["files"] = existing_files
        update["generated_code"] = existing_code

    updated = await storage.update_project(request.project_id, update)

    # MAPL: record error signal as user-specific negative-reward memory
    if _detect_error_signal(request.message):
        asyncio.create_task(_record_chat_mapl_memory(
            storage=storage,
            user_id=user_id,
            message=request.message,
            project=project,
            reward=-0.5,
            outcome=Outcome.FAILURE,
        ))

    realtime = _get_realtime(req)
    if realtime:
        payload: dict = {"reply": reply}
        if file_changes:
            payload["files_changed"] = list(file_changes.keys())
        await realtime.broadcast(request.project_id, "chat_message", payload)

    return AIChatResponse(
        reply=reply,
        project=ProjectResponse(**(updated or project)),
        intent=result.payload.get("intent", "general"),
        intent_label=result.payload.get("intent_label", "General"),
    )


@router.post("/score-prompt")
async def score_prompt_endpoint(
    body: dict,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Lightweight endpoint — no credit cost. Returns prompt quality score 0–100."""
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse(content={"score": 0, "label": "Weak", "feedback": [], "features": {}})
    return JSONResponse(content=score_prompt(prompt))


@router.post("/godot/generate", response_model=GodotGenerateResponse)
async def generate_godot_game(
    request: GodotGenerateRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> GodotGenerateResponse:
    await _enforce_rate_limit(current_user["user_id"])
    await _enforce_credits(current_user["user_id"], storage)
    project = await _require_owned_project(request.project_id, storage, current_user)
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


class FileActionRequest(BaseModel):
    project_id: str
    filename: str
    content: str
    action: str  # "explain" | "fix" | "improve"


@router.post("/file-action")
async def file_action(
    request: FileActionRequest,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    await _enforce_rate_limit(current_user["user_id"])
    await _enforce_credits(current_user["user_id"], storage)
    project = await _require_owned_project(request.project_id, storage, current_user)

    if request.action == "explain":
        prompt = f"Explain what this file does:\n\nFilename: {request.filename}\n\n```\n{request.content}\n```"
    elif request.action == "fix":
        prompt = f"Find and fix bugs in this file. Return the corrected code only:\n\nFilename: {request.filename}\n\n```\n{request.content}\n```"
    elif request.action == "improve":
        prompt = f"Suggest improvements for this file:\n\nFilename: {request.filename}\n\n```\n{request.content}\n```"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action '{request.action}'. Must be 'explain', 'fix', or 'improve'.")

    result = await ai_orchestrator.chat_reply(prompt, project=project, history=[])
    reply_text = result.payload.get("reply", "")

    history = _append_messages(project, prompt, reply_text)
    usage_logs = _append_usage_log(project, f"file-action:{request.action}", result.usage)
    update = {"ai_conversation": history, "ai_usage_logs": usage_logs}
    await storage.update_project(request.project_id, update)

    return JSONResponse(content={"reply": reply_text})


@router.post("/generate/stream")
async def generate_code_stream(
    request: AICodeRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Stream AI code generation progress as Server-Sent Events."""
    await _enforce_rate_limit(current_user["user_id"])
    await _enforce_credits(current_user["user_id"], storage)
    project = await _require_owned_project(request.project_id, storage, current_user)

    queue: asyncio.Queue = asyncio.Queue()
    agents = ["design", "scripts", "scenes", "assets", "assembler"]

    async def run_generation():
        try:
            # Simulate agent progress before blocking generation call
            for agent in agents:
                await queue.put({"type": "agent", "agent": agent, "status": "running"})
                await asyncio.sleep(0.5)
            result = await ai_orchestrator.generate_code(
                request.prompt,
                design_doc=project.get("design_doc"),
                history=project.get("ai_conversation", []),
                realtime=None,
                project_id=request.project_id,
            )
            # Save to DB (same logic as /generate)
            files = result.payload.get("files", {})
            versions = project.get("versions", [])
            versions.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "ai-stream",
                "files": list(files.keys()),
            })
            history = _append_messages(project, request.prompt, result.summary)
            usage_logs = _append_usage_log(project, "generate-stream", result.usage)
            update = {
                "generated_code": result.payload,
                "ai_conversation": history,
                "ai_usage_logs": usage_logs,
                "versions": versions[-_MAX_VERSIONS:],
                "status": "building",
            }
            updated = await storage.update_project(request.project_id, update)
            await storage.update_user_usage(
                current_user["user_id"], ai_tokens=int(result.usage.total_tokens or 0)
            )
            for agent in agents:
                await queue.put({"type": "agent", "agent": agent, "status": "complete"})
            proj_dict = ProjectResponse(**(updated or project)).model_dump()
            # Convert datetime objects to strings
            proj_dict = {
                k: str(v) if hasattr(v, "isoformat") else v
                for k, v in proj_dict.items()
            }
            success_prediction = predict_success(result.payload) if result.payload else {}
            await queue.put({"type": "done", "project": proj_dict, "success_prediction": success_prediction})
        except Exception as e:
            await queue.put({"type": "error", "message": str(e)})
        finally:
            await queue.put(None)  # sentinel

    async def event_stream():
        task = asyncio.create_task(run_generation())
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"
        await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/chat/stream")
async def chat_stream(
    request: AIChatRequest,
    req: Request,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Stream chat reply as Server-Sent Events, splitting reply into word-level chunks."""
    await _enforce_rate_limit(current_user["user_id"])
    await _enforce_credits(current_user["user_id"], storage)
    project = await _require_owned_project(request.project_id, storage, current_user)

    user_id = current_user["user_id"]
    user_sent_at = datetime.now(timezone.utc).isoformat()
    result = await ai_orchestrator.chat_reply(
        request.message,
        project=project,
        history=project.get("ai_conversation", []),
        user_id=user_id,
        storage=storage,
    )
    reply = result.payload.get("reply", "")
    file_changes: dict = result.payload.get("file_changes", {})

    history = _append_messages(project, request.message, reply, user_sent_at)
    usage_logs = _append_usage_log(project, "chat-stream", result.usage)
    update: dict = {"ai_conversation": history, "ai_usage_logs": usage_logs}

    # Apply file changes directly into the project
    if file_changes:
        existing_code = dict(project.get("generated_code") or {})
        existing_files = dict(existing_code.get("files", {}))
        existing_files.update(file_changes)
        existing_code["files"] = existing_files
        update["generated_code"] = existing_code

    updated = await storage.update_project(request.project_id, update)

    # MAPL: record error signal as user-specific negative-reward memory
    if _detect_error_signal(request.message):
        asyncio.create_task(_record_chat_mapl_memory(
            storage=storage,
            user_id=user_id,
            message=request.message,
            project=project,
            reward=-0.5,
            outcome=Outcome.FAILURE,
        ))

    proj_dict = ProjectResponse(**(updated or project)).model_dump()
    proj_dict = {
        k: str(v) if hasattr(v, "isoformat") else v
        for k, v in proj_dict.items()
    }

    async def event_stream():
        # Simulate streaming by yielding word-by-word chunks
        words = reply.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == 0 else " " + word
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            await asyncio.sleep(0.02)
        done_payload: dict = {
            "type": "done",
            "project": proj_dict,
            "intent": result.payload.get("intent", "general"),
            "intent_label": result.payload.get("intent_label", "General"),
        }
        if file_changes:
            done_payload["files_changed"] = list(file_changes.keys())
        yield f"data: {json.dumps(done_payload, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/download/{project_id}")
async def download_project_zip(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Download all generated project files as a ZIP archive."""
    project = await _require_owned_project(project_id, storage, current_user)
    generated_code = project.get("generated_code", {})
    files = generated_code.get("files", {})
    if not files:
        raise HTTPException(status_code=404, detail="No generated files to download")

    project_name = project.get("name", "untitled")
    zip_bytes = await asyncio.to_thread(zip_project_from_files, project_name, files)

    safe_name = "".join(c if (c.isalnum() or c in " _-") else "_" for c in project_name).strip() or "project"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )

_MAX_IMPORT_FILES = 200
_MAX_FILE_SIZE_BYTES = 512 * 1024  # 512 KB per file


def _validate_files(files: dict[str, str], operation: str = "import") -> None:
    """Enforce per-operation file count and size limits."""
    if len(files) > _MAX_IMPORT_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"{operation}: too many files ({len(files)}). Maximum is {_MAX_IMPORT_FILES}.",
        )
    for name, content in files.items():
        size = len(content.encode("utf-8"))
        if size > _MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"{operation}: file '{name}' is {size} bytes, max is {_MAX_FILE_SIZE_BYTES} bytes.",
            )


class _ImportFilesBody(BaseModel):
    files: dict[str, str]
    merge: bool = True  # True = merge with existing files; False = replace all


@router.post("/import/{project_id}", response_model=ProjectResponse)
async def import_files(
    project_id: str,
    body: _ImportFilesBody,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> ProjectResponse:
    """Import user-supplied source files into a project so the AI can modify them."""
    _validate_files(body.files, "import")
    project = await _require_owned_project(project_id, storage, current_user)

    existing_gc = project.get("generated_code") or {}
    if body.merge:
        merged = {**existing_gc.get("files", {}), **body.files}
    else:
        merged = body.files

    versions = project.get("versions", [])
    versions.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "user-import",
        "files": list(body.files.keys()),
    })
    versions = versions[-_MAX_VERSIONS:]

    update = {
        "generated_code": {**existing_gc, "files": merged},
        "status": "ready",
        "versions": versions,
    }
    updated = await storage.update_project(project_id, update)
    return ProjectResponse(**(updated or project))


class _SaveCodeBody(BaseModel):
    files: dict[str, str]


@router.patch("/code/{project_id}", response_model=ProjectResponse)
async def save_code(
    project_id: str,
    body: _SaveCodeBody,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> ProjectResponse:
    """Save manually edited source files back to the project."""
    _validate_files(body.files, "save-code")
    project = await _require_owned_project(project_id, storage, current_user)
    existing_gc = project.get("generated_code") or {}
    versions = project.get("versions", [])
    versions.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "manual-edit",
        "files": list(body.files.keys()),
    })
    versions = versions[-_MAX_VERSIONS:]
    update = {
        "generated_code": {**existing_gc, "files": body.files},
        "versions": versions,
    }
    updated = await storage.update_project(project_id, update)
    return ProjectResponse(**(updated or project))


@router.post("/open-folder/{project_id}")
async def open_folder(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Open the generated project folder in the system file explorer."""
    project = await _require_owned_project(project_id, storage, current_user)
    project_name = project.get("name", "untitled")
    result = await asyncio.to_thread(open_project_folder, project_name, project_id)
    status = 200 if result["success"] else 404
    return JSONResponse(content=result, status_code=status)


@router.post("/run-godot/{project_id}")
async def run_godot(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """Launch Godot editor with the generated project."""
    project = await _require_owned_project(project_id, storage, current_user)
    project_name = project.get("name", "untitled")
    result = await asyncio.to_thread(launch_godot, project_name, project_id)
    status = 200 if result["success"] else 404
    return JSONResponse(content=result, status_code=status)