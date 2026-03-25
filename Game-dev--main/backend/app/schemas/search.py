from typing import Literal, Optional
from pydantic import BaseModel
from app.schemas.project import ProjectResponse


class SearchResultItem(BaseModel):
    project: ProjectResponse
    score: float
    match_type: Literal["keyword", "game_type"]
    matched_terms: list[str]


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    query: str
    total: int
    keyword_hits: int
    ml_hits: int
    predicted_game_type: Optional[str] = None
    classifier_confidence: Optional[float] = None
