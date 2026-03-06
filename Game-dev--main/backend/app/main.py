import sys
print("starting main.py!!!", file=sys.stderr)

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes.ai import router as ai_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.preview import router as preview_router
from app.api.v1.routes.projects import router as projects_router
from app.api.v1.routes.s3 import router as s3_router
from app.services.realtime import RealtimeManager
from app.services.storage import StorageManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = StorageManager()
    await storage.connect()
    app.state.storage = storage
    app.state.realtime = RealtimeManager()
    yield
    await storage.close()


app = FastAPI(
    title="Game AI Platform API",
    version="0.1.0",
    description="Backend scaffold for AI game platform frontend integration.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict:
    return {"message": "Game AI Platform API is running"}


app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
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
        realtime.disconnect(project_id, websocket)
