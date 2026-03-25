import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import PLAN_LIMITS, settings

_ws_logger = logging.getLogger(__name__)

from app.api.v1.routes.ai import router as ai_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.preview import router as preview_router
from app.api.v1.routes.projects import router as projects_router
from app.api.v1.routes.s3 import router as s3_router
from app.api.v1.routes.users import router as users_router
from app.services.realtime import RealtimeManager
from app.services.storage import StorageManager

_startup_log = logging.getLogger("app.startup")


def _validate_startup_config() -> None:
    """Validate critical environment variables at startup.

    Hard-fails on security-critical misconfigurations in production mode.
    Logs warnings for missing-but-optional keys so operators know what
    features will be degraded.
    """
    is_prod = not settings.allow_inmemory_fallback

    # ── Hard failures (production only) ───────────────────────────────────────
    if is_prod and (not settings.jwt_secret_key or settings.jwt_secret_key == "dev-local-secret"):
        _startup_log.critical(
            "FATAL: JWT_SECRET_KEY is missing or set to the insecure default "
            "'dev-local-secret'. Generate a strong value with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        raise SystemExit(1)

    # ── AI provider warnings ───────────────────────────────────────────────────
    provider = settings.ai_provider.lower()
    if provider in ("gemini", "auto") and not settings.gemini_api_key:
        _startup_log.warning(
            "GEMINI_API_KEY is not set — Gemini features will be unavailable."
        )
    if provider in ("openai", "auto") and not settings.openai_api_key:
        _startup_log.warning(
            "OPENAI_API_KEY is not set — OpenAI features will be unavailable."
        )
    if provider == "local" and not settings.ai_local_base_url:
        _startup_log.warning(
            "AI_PROVIDER=local but AI_LOCAL_BASE_URL is not set — local AI will fail at runtime."
        )

    # ── Infrastructure warnings ────────────────────────────────────────────────
    if not settings.redis_url.strip():
        _startup_log.warning(
            "REDIS_URL not configured — rate limiting and brute-force protection use "
            "in-memory fallbacks (not safe for multi-worker deployments)."
        )
    if not settings.s3_bucket_name:
        _startup_log.warning(
            "S3_BUCKET_NAME not set — file upload/download features will be unavailable."
        )

    _startup_log.info("Startup config validation passed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _validate_startup_config()

    storage = StorageManager()
    try:
        await storage.connect()
    except Exception as exc:
        _startup_log.critical(
            "FATAL: Could not connect to MongoDB at %s — %s. "
            "Set ALLOW_INMEMORY_FALLBACK=true to use the in-memory store (dev only).",
            settings.mongodb_uri,
            exc,
        )
        raise SystemExit(1) from exc

    app.state.storage = storage
    app.state.realtime = RealtimeManager()

    # Start monthly credit reset scheduler
    async def _reset_credits():
        await storage.reset_all_monthly_credits(PLAN_LIMITS)

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(_reset_credits, "cron", day=1, hour=0, minute=0)
        scheduler.start()
        app.state.scheduler = scheduler
    except ImportError:
        logging.getLogger(__name__).warning(
            "apscheduler not installed — monthly credit reset disabled"
        )

    yield
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)
    await storage.close()
    from app.services.ai_providers import close_http_client
    await close_http_client()


app = FastAPI(
    title="Game AI Platform API",
    version="0.1.0",
    description="Backend scaffold for AI game platform frontend integration.",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Parse CORS_ORIGINS env var (comma-separated list or "*").
from app.core.config import settings as _settings  # noqa: E402

_raw_origins = _settings.cors_origins.strip()
_allow_origins: list[str] = (
    ["*"] if _raw_origins == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)

# allow_credentials=True is incompatible with allow_origins=["*"] per the CORS spec —
# browsers reject such responses. Since we use Bearer tokens (not cookies) we don't
# need allow_credentials at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── HTTPS redirect + HSTS ─────────────────────────────────────────────────────
# Enable with ENFORCE_HTTPS=true only when the app terminates TLS directly.
# Keep false (default) when a reverse proxy (nginx, Caddy, ALB) handles TLS,
# because the proxy already redirects HTTP and the app only sees plain HTTP.
if _settings.enforce_https:
    from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

    app.add_middleware(HTTPSRedirectMiddleware)

    @app.middleware("http")
    async def _add_hsts_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: log the full traceback and return a generic 500.

    Returning the raw exception message to the client would leak internal
    implementation details. The full traceback is written to the server log
    where it is available to operators.
    """
    _ws_logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


@app.get("/")
async def root() -> dict:
    return {"message": "Game AI Platform API is running"}


app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(preview_router, prefix="/api/v1")
app.include_router(s3_router, prefix="/api/v1")


@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str) -> None:
    realtime: RealtimeManager = websocket.app.state.realtime
    await realtime.connect(project_id, websocket)
    try:
        while True:
            client_message = await websocket.receive_text()
            await realtime.broadcast(project_id, "client_message", {"data": client_message})
    except WebSocketDisconnect:
        realtime.disconnect(project_id, websocket)
    except Exception:
        _ws_logger.exception("Unexpected error on WebSocket for project %s", project_id)
        realtime.disconnect(project_id, websocket)
