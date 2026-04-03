from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.project import ProjectResponse


class AIDesignRequest(BaseModel):
    project_id: str
    prompt: str


class AIDesignResponse(BaseModel):
    summary: str = ""
    design_doc: dict = Field(default_factory=dict)
    project: Optional[ProjectResponse] = None
    prompt_score: dict = Field(default_factory=dict)       # from PromptScorer
    success_prediction: dict = Field(default_factory=dict) # from SuccessPredictor


class AICodeRequest(BaseModel):
    project_id: str
    prompt: str
    framework: str = "phaser"


class AICodeResponse(BaseModel):
    generated_code: dict = Field(default_factory=dict)
    project: Optional[ProjectResponse] = None


class AIChatRequest(BaseModel):
    project_id: str
    message: str


class AIChatResponse(BaseModel):
    reply: str = ""
    project: Optional[ProjectResponse] = None
    intent: str = ""        # from IntentClassifier e.g. "fix_bug"
    intent_label: str = ""  # human label e.g. "Fix Bug"


class GodotGenerateRequest(BaseModel):
    project_id: str
    prompt: str


class GodotGenerateResponse(BaseModel):
    status: str = ""
    design_doc: dict = Field(default_factory=dict)
    file_urls: list = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
    errors: list = Field(default_factory=list)
