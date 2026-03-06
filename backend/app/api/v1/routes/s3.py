"""S3 file management routes.

Provides endpoints for:
- Uploading project files to S3 (under ``{username}/{project_name}/``)
- Listing a user's S3 files
- Listing files for a specific project
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_storage
from app.services.s3_storage import s3_storage
from app.services.storage import StorageManager

router = APIRouter(prefix="/s3", tags=["s3"])


class S3UploadRequest(BaseModel):
    project_id: str
    files: dict[str, str] = Field(description="Map of filename → file content")


class S3FileInfo(BaseModel):
    key: str | None = None
    url: str | None = None
    size: int | None = None
    last_modified: str | None = None
    error: str | None = None


class S3UploadResponse(BaseModel):
    uploaded: list[S3FileInfo] = Field(default_factory=list)


class S3ListResponse(BaseModel):
    files: list[S3FileInfo] = Field(default_factory=list)


@router.post("/upload", response_model=S3UploadResponse)
async def upload_project_files(
    request: S3UploadRequest,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> S3UploadResponse:
    """Upload files to S3 under ``{username}/{project_name}/``."""
    project = await storage.get_project(request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    username = current_user.get("username", "unknown")
    project_name = project.get("name", "untitled")

    if not request.files:
        raise HTTPException(status_code=400, detail="No files provided")

    results = await s3_storage.upload_project_files(username, project_name, request.files)
    return S3UploadResponse(uploaded=[S3FileInfo(**r) for r in results])


@router.get("/files", response_model=S3ListResponse)
async def list_user_files(
    current_user: dict = Depends(get_current_user),
) -> S3ListResponse:
    """List all files in S3 belonging to the current user."""
    username = current_user.get("username", "unknown")
    files = await s3_storage.list_user_files(username)
    return S3ListResponse(files=[S3FileInfo(**f) for f in files])


@router.get("/files/{project_id}", response_model=S3ListResponse)
async def list_project_files(
    project_id: str,
    storage: StorageManager = Depends(get_storage),
    current_user: dict = Depends(get_current_user),
) -> S3ListResponse:
    """List all files in S3 for a specific project."""
    project = await storage.get_project(project_id)
    username = current_user.get("username", "unknown")
    project_name = project.get("name", "untitled") if project else "untitled"
    files = await s3_storage.list_project_files(username, project_name)
    return S3ListResponse(files=[S3FileInfo(**f) for f in files])
