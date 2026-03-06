from fastapi import APIRouter, Depends

from app.api.deps import get_storage
from app.schemas.dashboard import (
    ArchitectureItem,
    DashboardSummary,
    FeatureItem,
    MetricItem,
    RoadmapItem,
)
from app.services.storage import StorageManager

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    storage: StorageManager = Depends(get_storage),
) -> DashboardSummary:
    user_count = str(await storage.count_users())
    project_count = str(await storage.count_projects())

    return DashboardSummary(
        brand_name="ForgeAI",
        hero_badge="AI game studio in one workspace",
        hero_title="Build, test, and ship AI-generated games at production speed",
        hero_subtext=(
            "Based on your plan: React + FastAPI + AI orchestration + game engine service. "
            "From prompt to playable preview with architecture-ready workflows."
        ),
        metrics=[
            MetricItem(name="Registered Users", status=user_count),
            MetricItem(name="Projects Created", status=project_count),
            MetricItem(name="AI Orchestrator", status="Ready"),
            MetricItem(name="Build Runtime", status="Live Preview"),
        ],
        trusted_by="",
        features=[
            FeatureItem(
                title="Prompt-to-Design System",
                description="Converts user intent into structured game docs: entities, loops, mechanics, and technical requirements.",
            ),
            FeatureItem(
                title="Code Generation Workspace",
                description="Monaco-based multi-file editing with AI-assisted generation for Phaser, JavaScript, and engine-compatible modules.",
            ),
            FeatureItem(
                title="Real-time Preview Engine",
                description="Live game preview with hot updates and runtime feedback connected through WebSocket orchestration.",
            ),
            FeatureItem(
                title="Asset & Build Pipeline",
                description="Asset processing, AI recommendations, Redis-backed tasks, and deploy-ready packaging aligned to your phase plan.",
            ),
        ],
        architecture=[
            ArchitectureItem(title="Frontend Layer", description="React + TypeScript + Vite, panel-based editor and preview UI."),
            ArchitectureItem(title="API Gateway + Services", description="FastAPI auth, games, AI orchestration, and assets microservices."),
            ArchitectureItem(title="AI + Workers", description="Orchestrator agent flow with Celery workers and Redis queues."),
            ArchitectureItem(title="Engine + Data", description="C++ runtime, MongoDB project storage, vector search, and S3 assets."),
        ],
        roadmap=[
            RoadmapItem(phase="Phase 1", window="Weeks 1-3", description="Repository setup, Docker environment, CI/CD baseline, infra bootstrapping."),
            RoadmapItem(phase="Phase 2", window="Weeks 4-6", description="Core backend APIs, project schema, auth, CRUD workflows, and websocket channel."),
            RoadmapItem(phase="Phase 3", window="Weeks 7-9", description="AI agent orchestration, template-driven generation, and engine integration."),
            RoadmapItem(phase="Phase 4", window="Weeks 10-12", description="Frontend editor suite: chat, code editor, preview panel, and asset manager."),
            RoadmapItem(phase="Phase 5", window="Weeks 13-16", description="Integration testing, Kubernetes deployment, monitoring, and production hardening."),
        ],
    )
