from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
    framework: str = "phaser"


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    framework: Optional[str] = None
    status: Optional[str] = None
    design_doc: Optional[dict] = None
    generated_code: Optional[dict] = None
    assets: Optional[list] = None


class ProjectResponse(BaseModel):
    project_id: str = ""
    user_id: str = ""
    name: str = ""
    description: str = ""
    framework: str = "phaser"
    status: str = "draft"
    design_doc: dict = Field(default_factory=dict)
    generated_code: dict = Field(default_factory=dict)
    assets: list = Field(default_factory=list)
    ai_conversation: list = Field(default_factory=list)
    ai_usage_logs: list = Field(default_factory=list)
    versions: list = Field(default_factory=list)
    deployment: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    is_public: bool = False
    likes: int = 0
    plays: int = 0
    user_liked: bool = False  # computed server-side, never stored
