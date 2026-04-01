"""MAPL (Memory-Augmented Prompt Learning) API routes.

Provides endpoints for:
- Submitting generation feedback (reward signals)
- Querying MAPL memory retrieval for a prompt
- Viewing MAPL subsystem statistics
- Triggering memory optimization
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_storage
from app.schemas.mapl import (
    MAPLFeedbackRequest,
    MAPLRetrievalResponse,
    MAPLStatsResponse,
    MemoryState,
    ScoredMemory,
)
from app.services.mapl_service import mapl_service
from app.services.storage import StorageManager

router = APIRouter(prefix="/mapl", tags=["mapl"])
logger = logging.getLogger(__name__)


@router.post("/feedback", summary="Submit generation feedback")
async def submit_feedback(
    body: MAPLFeedbackRequest,
    user: dict = Depends(get_current_user),
    storage: StorageManager = Depends(get_storage),
) -> dict[str, Any]:
    """Record reward feedback for a generated game.

    The MAPL subsystem stores this as an experience tuple and promotes
    high-reward memories to long-term storage for future prompt augmentation.
    """
    # Verify project exists and user owns it
    project = await storage.get_project(body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your project")

    memory = await mapl_service.record_feedback(
        project_id=body.project_id,
        reward=body.reward,
        outcome=body.outcome,
        storage=storage,
        user_id=user["user_id"],
        notes=body.notes,
    )

    if not memory:
        raise HTTPException(status_code=400, detail="Could not record feedback")

    return {
        "status": "recorded",
        "memory_id": memory.memory_id,
        "tier": memory.tier.value,
        "reward": memory.reward,
    }


@router.post("/retrieve", summary="Retrieve relevant memories for a prompt")
async def retrieve_memories(
    body: dict[str, Any],
    user: dict = Depends(get_current_user),
    storage: StorageManager = Depends(get_storage),
) -> MAPLRetrievalResponse:
    """Query the MAPL memory for past experiences relevant to a given prompt.

    Used by the frontend to show users what the system has learned
    from past generations of similar games.
    """
    prompt = body.get("prompt", "")
    game_type = body.get("game_type", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    state = MemoryState(prompt=prompt, game_type=game_type)

    top_memories = await mapl_service.score_and_rank(
        current_state=state,
        storage=storage,
        user_id=user["user_id"],
    )

    # Build the prompt augmentation block
    _, augmented_memories = await mapl_service.build_augmented_prompt(
        current_state=state,
        base_prompt=prompt,
        storage=storage,
        user_id=user["user_id"],
    )

    # Format prompt augmentation text
    prompt_aug = ""
    if augmented_memories:
        lines = []
        for i, sm in enumerate(augmented_memories, 1):
            mem = sm.memory
            lines.append(
                f"{i}. {mem.state.game_type} ({mem.outcome.value}, "
                f"reward={mem.reward:.1f})"
            )
        prompt_aug = "\n".join(lines)

    return MAPLRetrievalResponse(
        query_state=state.model_dump(),
        memories=top_memories,
        prompt_augmentation=prompt_aug,
    )


@router.get("/stats", summary="MAPL subsystem statistics")
async def get_stats(
    user: dict = Depends(get_current_user),
    storage: StorageManager = Depends(get_storage),
) -> MAPLStatsResponse:
    """Return statistics about the MAPL memory subsystem."""
    stats = await mapl_service.get_stats(storage)
    return MAPLStatsResponse(**stats)


@router.post("/optimize", summary="Trigger memory optimization")
async def trigger_optimization(
    user: dict = Depends(get_current_user),
    storage: StorageManager = Depends(get_storage),
) -> dict[str, Any]:
    """Manually trigger MAPL memory optimization.

    Runs forgetting (prune old low-value memories), clustering
    (cap per-type counts), and summarization.
    """
    result = await mapl_service.optimize_memory(storage)
    return {"status": "optimized", **result}
