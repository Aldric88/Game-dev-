"""Pydantic schemas for the Memory-Augmented Prompt Learning (MAPL) subsystem.

Each interaction is stored as a structured experience tuple:
    M_i = (s_i, a_i, r_i, o_i)
where s = state, a = action, r = reward, o = outcome.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────

class MemoryTier(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"


class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


# ── Core Memory Tuple ─────────────────────────────────────────────────────────

class MemoryState(BaseModel):
    """State representation at the time of interaction."""
    prompt: str = Field(..., description="Original user prompt / game description")
    game_type: str = Field("", description="Predicted or confirmed game type")
    entity_count: int = Field(0, description="Number of entities in the design")
    provider: str = Field("", description="AI provider used")
    context_features: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional state features (mechanics, visual_style, etc.)",
    )


class MemoryAction(BaseModel):
    """Action taken by the system."""
    action_type: str = Field(..., description="Type: design, generate, chat, file_action")
    prompt_template: str = Field("", description="Template/strategy used for the prompt")
    temperature: float = Field(0.7, description="Temperature used for generation")
    provider_chain: list[str] = Field(
        default_factory=list,
        description="Ordered list of providers attempted",
    )


class ExperienceMemory(BaseModel):
    """Single experience tuple: M_i = (s_i, a_i, r_i, o_i)."""
    memory_id: str = Field("", description="Unique identifier")
    state: MemoryState
    action: MemoryAction
    reward: float = Field(
        0.0,
        ge=-1.0,
        le=1.0,
        description="Reward value: 1.0 = perfect, 0.0 = neutral, -1.0 = failure",
    )
    outcome: Outcome = Field(Outcome.SUCCESS, description="Discrete outcome label")
    tier: MemoryTier = Field(MemoryTier.SHORT_TERM, description="Memory tier")
    timestamp: str = Field("", description="ISO timestamp of creation")
    user_id: str = Field("", description="User who generated this experience")
    access_count: int = Field(0, description="Times retrieved for prompt augmentation")


class ScoredMemory(BaseModel):
    """Memory with computed relevance score for retrieval."""
    memory: ExperienceMemory
    similarity: float = Field(0.0, description="Cosine / token similarity to query")
    reward_signal: float = Field(0.0, description="Reward contribution")
    temporal_decay: float = Field(0.0, description="Recency decay factor")
    utility: float = Field(0.0, description="Deviation from mean reward (surprisal)")
    total_score: float = Field(0.0, description="Weighted composite score")


# ── API Request / Response ─────────────────────────────────────────────────────

class MAPLFeedbackRequest(BaseModel):
    """User or system submits feedback on a generation outcome."""
    project_id: str = Field(..., description="Project that was generated")
    reward: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Reward signal: 1.0 = excellent, 0.0 = neutral, -1.0 = bad",
    )
    outcome: Outcome = Field(Outcome.SUCCESS)
    notes: str = Field("", max_length=500, description="Optional human feedback note")


class MAPLStatsResponse(BaseModel):
    """Summary statistics for the MAPL subsystem."""
    short_term_count: int = Field(0)
    long_term_count: int = Field(0)
    total_memories: int = Field(0)
    avg_reward: float = Field(0.0)
    top_game_types: list[dict[str, Any]] = Field(default_factory=list)
    last_optimization: str = Field("")


class MAPLRetrievalResponse(BaseModel):
    """Top-k memories retrieved for a given query state."""
    query_state: dict[str, Any] = Field(default_factory=dict)
    memories: list[ScoredMemory] = Field(default_factory=list)
    prompt_augmentation: str = Field("", description="Formatted past-experience block for LLM injection")
