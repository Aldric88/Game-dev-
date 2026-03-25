from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_current_user, get_current_user_optional, get_storage
from app.schemas.project import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.schemas.search import SearchResponse, SearchResultItem
from app.services.recommendation_service import recommendation_service
from app.services.s3_storage import s3_storage
from app.services.search_service import search_service
from app.services.storage import StorageManager

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_defaults(user_id: str, name: str, description: str, framework: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "user_id": user_id,
        "name": name.strip(),
        "description": description,
        "framework": framework.lower(),
        "status": "draft",
        "deployment": {"status": "not_deployed"},
        "design_doc": {},
        "generated_code": {},
        "assets": [],
        "ai_conversation": [],
        "ai_usage_logs": [],
        "versions": [],
        "created_at": now,
        "updated_at": now,
        "is_public": False,
        "likes": 0,
        "plays": 0,
        "liked_by": [],
    }


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectResponse)
async def create_project(
    request: ProjectCreateRequest,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> ProjectResponse:
    payload = _project_defaults(
        user_id=current_user["user_id"],
        name=request.name,
        description=request.description,
        framework=request.framework,
    )
    project = await storage.create_project(payload)
    return ProjectResponse(**project)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> list[ProjectResponse]:
    projects = await storage.list_projects(current_user["user_id"])
    return [ProjectResponse(**p) for p in projects]


@router.get("/search", response_model=SearchResponse)
async def search_projects(
    q: Optional[str] = Query(default="", description="Search query"),
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> SearchResponse:
    """
    Hybrid search over the user's projects.
    Stage 1: keyword match across name, description, game_type, mechanics, framework.
    Stage 2: ML classifier predicts game type → finds similar projects not in Stage 1.
    Keyword results always rank above ML results.
    """
    raw_projects = await storage.list_projects(current_user["user_id"])
    project_dicts = [p if isinstance(p, dict) else dict(p) for p in raw_projects]

    result = search_service.search(q or "", project_dicts)

    # Fire-and-forget: persist ML signal for "For You" recommendations
    import asyncio
    gt   = result.get("predicted_game_type")
    conf = result.get("classifier_confidence") or 0.0
    if q and gt and conf >= 0.50:
        asyncio.create_task(storage.add_search_event(
            current_user["user_id"],
            {
                "query": q,
                "predicted_game_type": gt,
                "confidence": conf,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ))

    items = [
        SearchResultItem(
            project=ProjectResponse(**item["project"]),
            score=item["score"],
            match_type=item["match_type"],
            matched_terms=item["matched_terms"],
        )
        for item in result["results"]
    ]

    return SearchResponse(
        results=items,
        query=result["query"],
        total=result["total"],
        keyword_hits=result["keyword_hits"],
        ml_hits=result["ml_hits"],
        predicted_game_type=result["predicted_game_type"],
        classifier_confidence=result["classifier_confidence"],
    )


@router.get("/discover", response_model=list[ProjectResponse])
async def discover_projects(
    q: Optional[str] = Query(default="", description="Search public projects"),
    limit: int = Query(default=50, ge=1, le=200),
    storage: StorageManager = Depends(get_storage),
    current_user: dict | None = Depends(get_current_user_optional),
) -> list[ProjectResponse]:
    """Return public projects sorted by likes. Optional text search and limit."""
    projects = await storage.list_public_projects(search=(q or "").strip(), limit=limit)
    user_id = current_user["user_id"] if current_user else None
    result = []
    for p in projects:
        resp = ProjectResponse(**p)
        if user_id:
            resp.user_liked = user_id in p.get("liked_by", [])
        result.append(resp)
    return result


@router.get("/recommendations", response_model=list[ProjectResponse])
async def get_recommendations(
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> list[ProjectResponse]:
    """Return personalised public project recommendations for the current user."""
    import asyncio
    user_id = current_user["user_id"]

    user_projects, public_projects, liked_ids, search_history = await asyncio.gather(
        storage.list_projects(user_id),
        storage.list_public_projects(limit=200),
        storage.get_user_liked_project_ids(user_id),
        storage.get_search_history(user_id),
    )

    liked_set   = set(liked_ids)
    liked_projects = [p for p in public_projects if p.get("project_id") in liked_set]

    recs = recommendation_service.recommend(
        user_id=user_id,
        user_projects=user_projects,
        liked_project_ids=liked_ids,
        liked_projects=liked_projects,
        search_history=search_history,
        public_projects=public_projects,
        limit=10,
    )

    user_id_str = str(user_id)
    result = []
    for p in recs:
        resp = ProjectResponse(**p)
        resp.user_liked = user_id_str in p.get("liked_by", [])
        result.append(resp)
    return result


@router.patch("/{project_id}/visibility", response_model=ProjectResponse)
async def toggle_visibility(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> ProjectResponse:
    """Toggle a project between public and private. Owner only."""
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("user_id") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your project")
    updated = await storage.update_project(project_id, {"is_public": not project.get("is_public", False)})
    return ProjectResponse(**(updated or project))


@router.post("/{project_id}/like")
async def toggle_like(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Like or unlike a public project. Returns {likes, liked}."""
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.get("is_public", False):
        raise HTTPException(status_code=403, detail="Project is not public")
    result = await storage.toggle_like(project_id, current_user["user_id"])
    return result


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict | None = Depends(get_current_user_optional),
) -> ProjectResponse:
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(**project)


@router.post("/{project_id}/duplicate", status_code=status.HTTP_201_CREATED, response_model=ProjectResponse)
async def duplicate_project(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> ProjectResponse:
    source = await storage.get_project(project_id)
    if not source:
        raise HTTPException(status_code=404, detail="Project not found")
    if source.get("user_id") != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": current_user["user_id"],
        "name": f"{source.get('name', 'Untitled')} (copy)",
        "description": source.get("description", ""),
        "framework": source.get("framework", ""),
        "status": "draft",
        "deployment": source.get("deployment", {"status": "not_deployed"}),
        "design_doc": source.get("design_doc", {}),
        "generated_code": source.get("generated_code", {}),
        "assets": source.get("assets", []),
        "ai_conversation": [],
        "ai_usage_logs": [],
        "versions": [],
        "created_at": now,
        "updated_at": now,
    }
    project = await storage.create_project(payload)
    return ProjectResponse(**project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> ProjectResponse:
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = {k: v for k, v in request.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No update payload provided")

    # If code is being saved, push a version snapshot and attempt S3 upload
    if "generated_code" in update_data:
        versions = project.get("versions", [])
        versions.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "manual-code-save",
            "files": list(update_data["generated_code"].get("files", {}).keys()),
        })
        update_data["versions"] = versions

        files = update_data["generated_code"].get("files", {})
        if files:
            username = current_user.get("username", "unknown")
            project_name = project.get("name", "untitled")
            try:
                await s3_storage.upload_project_files(username, project_name, files)
            except Exception:
                import logging
                logging.getLogger(__name__).warning("S3 upload on save failed")

    updated = await storage.update_project(project_id, update_data)
    return ProjectResponse(**(updated or project))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> Response:
    project = await storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await storage.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
