from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, get_current_user_optional, get_storage
from app.schemas.project import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.services.s3_storage import s3_storage
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
