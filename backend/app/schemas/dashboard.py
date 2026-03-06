from pydantic import BaseModel, Field


class MetricItem(BaseModel):
    name: str = ""
    status: str = ""


class FeatureItem(BaseModel):
    title: str = ""
    description: str = ""


class ArchitectureItem(BaseModel):
    title: str = ""
    description: str = ""


class RoadmapItem(BaseModel):
    phase: str = ""
    window: str = ""
    description: str = ""


class DashboardSummary(BaseModel):
    brand_name: str = "ForgeAI"
    hero_badge: str = ""
    hero_title: str = ""
    hero_subtext: str = ""
    metrics: list = Field(default_factory=list)
    trusted_by: str = ""
    features: list = Field(default_factory=list)
    architecture: list = Field(default_factory=list)
    roadmap: list = Field(default_factory=list)
