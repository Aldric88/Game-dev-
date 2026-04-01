"""Memory-Augmented Prompt Learning (MAPL) service.

Implements the full MAPL framework from Section 5 of the paper:

- Dual memory architecture (short-term + long-term)
- Reward-aware memory scoring (Eq. 3)
- Memory retrieval with similarity threshold (Eq. 2)
- Action-feedback loop (Eq. 4-5)
- Memory optimization (summarization, clustering, forgetting)

The service operates entirely at inference time — no parameter updates
are needed, making it compatible with black-box LLM APIs.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from app.services.storage import StorageManager

from app.schemas.mapl import (
    ExperienceMemory,
    MemoryAction,
    MemoryState,
    MemoryTier,
    Outcome,
    ScoredMemory,
)

logger = logging.getLogger(__name__)

# ── Scoring hyper-parameters (Eq. 3) ──────────────────────────────────────────
# Score_i = α·Sim(s_t, s_i) + β·r_i + γ·e^{-λ(t-t_i)} + δ·U_i

ALPHA = 0.40   # similarity weight
BETA = 0.30    # reward weight
GAMMA = 0.15   # temporal decay weight
DELTA = 0.15   # utility (surprisal) weight
LAMBDA = 0.05  # decay rate (per hour)

# Retrieval config
SIMILARITY_THRESHOLD = 0.25   # τ — minimum similarity to be a candidate (Eq. 2)
TOP_K = 5                     # number of memories injected into prompt
SHORT_TERM_CAPACITY = 50      # max entries in short-term memory
LONG_TERM_PROMOTION_REWARD = 0.6  # min reward to promote to long-term
FORGETTING_AGE_HOURS = 720    # 30 days — short-term memories older than this are pruned


# ── Token-overlap similarity ──────────────────────────────────────────────────

_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might can could of in to for with on at by from as into "
    "through during before after above below between under again further then "
    "once here there when where why how all both each few more most other some "
    "such no nor not only own same so than too very and but or if".split()
)


def _tokenize(text: str) -> set[str]:
    """Lowercase tokenize, strip stop words, min 2 chars."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) >= 2 and t not in _STOP_WORDS}


def _token_similarity(text_a: str, text_b: str) -> float:
    """Jaccard-like token overlap similarity in [0, 1]."""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _state_similarity(current: MemoryState, stored: MemoryState) -> float:
    """Composite similarity between two states.

    Combines prompt text similarity with exact game-type match bonus.
    """
    text_sim = _token_similarity(current.prompt, stored.prompt)
    type_bonus = 0.2 if (
        current.game_type
        and current.game_type == stored.game_type
    ) else 0.0
    return min(1.0, text_sim + type_bonus)


# ── MAPL Service ───────────────────────────────────────────────────────────────

class MAPLService:
    """Memory-Augmented Prompt Learning engine.

    Maintains a dual-memory structure:
      - Short-Term Memory: recent interactions for fast updates
      - Long-Term Memory: high-value experiences persisted in MongoDB
    """

    def __init__(self) -> None:
        # Short-term memory: in-process list (fast, ephemeral per worker)
        self._short_term: list[ExperienceMemory] = []
        self._lock = asyncio.Lock()
        self._mean_reward: float = 0.0
        self._reward_count: int = 0
        self._last_optimization: str = ""

    # ── Memory Storage (Eq. 5) ─────────────────────────────────────────────

    async def store_memory(
        self,
        state: MemoryState,
        action: MemoryAction,
        reward: float,
        outcome: Outcome,
        user_id: str,
        storage: "StorageManager",
    ) -> ExperienceMemory:
        """Store a new experience: M_new = (s_t, a_t, r_t, o_t)."""
        now = datetime.now(timezone.utc)
        memory = ExperienceMemory(
            memory_id=uuid4().hex[:16],
            state=state,
            action=action,
            reward=max(-1.0, min(1.0, reward)),
            outcome=outcome,
            tier=MemoryTier.SHORT_TERM,
            timestamp=now.isoformat(),
            user_id=user_id,
        )

        # Update running mean reward
        self._reward_count += 1
        self._mean_reward += (reward - self._mean_reward) / self._reward_count

        # Add to short-term
        async with self._lock:
            self._short_term.append(memory)
            # Capacity enforcement
            if len(self._short_term) > SHORT_TERM_CAPACITY:
                self._short_term = self._short_term[-SHORT_TERM_CAPACITY:]

        # Promote high-reward memories to long-term (MongoDB)
        if reward >= LONG_TERM_PROMOTION_REWARD:
            memory_lt = memory.model_copy(update={"tier": MemoryTier.LONG_TERM})
            await storage.add_mapl_memory(memory_lt.model_dump())
            logger.info(
                "MAPL: Promoted memory %s to long-term (reward=%.2f)",
                memory.memory_id, reward,
            )

        return memory

    # ── Memory Retrieval (Eq. 2) ───────────────────────────────────────────

    async def retrieve_candidates(
        self,
        current_state: MemoryState,
        storage: "StorageManager",
        user_id: str = "",
    ) -> list[ExperienceMemory]:
        """Retrieve candidate memories: C = {M_i | Sim(s_t, s_i) > τ}."""
        candidates: list[ExperienceMemory] = []

        # Search short-term memory
        async with self._lock:
            for mem in self._short_term:
                sim = _state_similarity(current_state, mem.state)
                if sim > SIMILARITY_THRESHOLD:
                    candidates.append(mem)

        # Search long-term memory (MongoDB)
        lt_docs = await storage.get_mapl_memories(user_id=user_id, limit=200)
        for doc in lt_docs:
            try:
                mem = ExperienceMemory(**doc)
                sim = _state_similarity(current_state, mem.state)
                if sim > SIMILARITY_THRESHOLD:
                    candidates.append(mem)
            except Exception:
                continue

        return candidates

    # ── Reward-Aware Scoring (Eq. 3) ───────────────────────────────────────

    def _compute_score(
        self,
        current_state: MemoryState,
        memory: ExperienceMemory,
        now: datetime | None = None,
    ) -> ScoredMemory:
        """Compute composite score:
        Score_i = α·Sim(s_t, s_i) + β·r_i + γ·e^{-λ(t-t_i)} + δ·U_i
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # Similarity term
        similarity = _state_similarity(current_state, memory.state)

        # Reward term (normalized to [0, 1])
        reward_signal = (memory.reward + 1.0) / 2.0

        # Temporal decay: e^{-λ(t - t_i)}  where (t - t_i) is in hours
        try:
            mem_time = datetime.fromisoformat(memory.timestamp)
            if mem_time.tzinfo is None:
                mem_time = mem_time.replace(tzinfo=timezone.utc)
            delta_hours = (now - mem_time).total_seconds() / 3600.0
        except (ValueError, TypeError):
            delta_hours = 0.0
        temporal_decay = math.exp(-LAMBDA * max(0.0, delta_hours))

        # Utility: |r_i - r̄|  (surprisal — how unusual is this reward?)
        utility = abs(memory.reward - self._mean_reward)

        # Composite score
        total = (
            ALPHA * similarity
            + BETA * reward_signal
            + GAMMA * temporal_decay
            + DELTA * utility
        )

        return ScoredMemory(
            memory=memory,
            similarity=similarity,
            reward_signal=reward_signal,
            temporal_decay=temporal_decay,
            utility=utility,
            total_score=total,
        )

    async def score_and_rank(
        self,
        current_state: MemoryState,
        storage: "StorageManager",
        user_id: str = "",
        k: int = TOP_K,
    ) -> list[ScoredMemory]:
        """Full retrieval + scoring pipeline: returns top-k scored memories."""
        candidates = await self.retrieve_candidates(current_state, storage, user_id)
        if not candidates:
            return []

        now = datetime.now(timezone.utc)
        scored = [self._compute_score(current_state, mem, now) for mem in candidates]
        scored.sort(key=lambda s: s.total_score, reverse=True)
        return scored[:k]

    # ── Prompt Augmentation ────────────────────────────────────────────────

    async def build_augmented_prompt(
        self,
        current_state: MemoryState,
        base_prompt: str,
        storage: "StorageManager",
        user_id: str = "",
        k: int = TOP_K,
    ) -> tuple[str, list[ScoredMemory]]:
        """Build a prompt augmented with top-k past experiences.

        Returns (augmented_prompt, scored_memories) so callers can log what
        memories were used.

        Implements: a_t = f(Prompt(s_t, M_k))  (Eq. 4)
        """
        top_memories = await self.score_and_rank(current_state, storage, user_id, k)
        if not top_memories:
            return base_prompt, []

        # Increment access counts
        for sm in top_memories:
            sm.memory.access_count += 1

        # Format experience block for injection
        experience_lines = ["PAST EXPERIENCES (use these to improve your response):"]
        for i, sm in enumerate(top_memories, 1):
            mem = sm.memory
            outcome_str = "success" if mem.outcome == Outcome.SUCCESS else "failure"
            experience_lines.append(
                f"{i}. Game type '{mem.state.game_type}' + "
                f"{mem.action.action_type} → {outcome_str} "
                f"(reward: {mem.reward:.1f}, relevance: {sm.total_score:.2f})"
            )
            # Add specific lessons from context
            if mem.state.context_features:
                mechanics = mem.state.context_features.get("mechanics", [])
                if mechanics:
                    if mem.outcome == Outcome.SUCCESS:
                        experience_lines.append(
                            f"   ✓ Effective mechanics: {', '.join(mechanics[:3])}"
                        )
                    else:
                        experience_lines.append(
                            f"   ✗ Avoid these mechanics together: {', '.join(mechanics[:3])}"
                        )

        experience_block = "\n".join(experience_lines) + "\n\n"
        augmented = f"{experience_block}CURRENT REQUEST:\n{base_prompt}"

        return augmented, top_memories

    # ── Feedback Loop (Eq. 4-5) ────────────────────────────────────────────

    async def record_feedback(
        self,
        project_id: str,
        reward: float,
        outcome: Outcome,
        storage: "StorageManager",
        user_id: str = "",
        notes: str = "",
    ) -> ExperienceMemory | None:
        """Record feedback for the most recent generation associated with a project.

        Looks up the project to reconstruct the state, then stores the memory
        with the given reward and outcome.
        """
        project = await storage.get_project(project_id)
        if not project:
            return None

        design_doc = project.get("design_doc", {})
        prompt = design_doc.get("summary", project.get("description", ""))
        game_type = design_doc.get("game_type", "")
        entities = design_doc.get("entities", [])
        mechanics = design_doc.get("mechanics", [])

        state = MemoryState(
            prompt=prompt,
            game_type=game_type,
            entity_count=len(entities),
            provider=project.get("ai_usage_logs", [{}])[-1].get("provider", "") if project.get("ai_usage_logs") else "",
            context_features={
                "mechanics": mechanics,
                "visual_style": design_doc.get("visual_style", {}),
                "entity_names": [
                    e.get("name", "") if isinstance(e, dict) else str(e)
                    for e in entities[:10]
                ],
            },
        )

        action = MemoryAction(
            action_type="generate",
            temperature=0.7,
        )

        memory = await self.store_memory(
            state=state,
            action=action,
            reward=reward,
            outcome=outcome,
            user_id=user_id or project.get("user_id", ""),
            storage=storage,
        )

        logger.info(
            "MAPL: Feedback recorded for project %s — reward=%.2f outcome=%s",
            project_id, reward, outcome.value,
        )
        return memory

    # ── Memory Optimization ────────────────────────────────────────────────

    async def optimize_memory(self, storage: "StorageManager") -> dict[str, Any]:
        """Run memory optimization: summarization, clustering, forgetting.

        Called periodically or when memory exceeds thresholds.
        """
        now = datetime.now(timezone.utc)
        stats: dict[str, Any] = {"pruned_short_term": 0, "pruned_long_term": 0, "clustered": 0}

        # ── 1. Forgetting: prune old, low-value short-term memories ───────
        async with self._lock:
            before_count = len(self._short_term)
            kept: list[ExperienceMemory] = []
            for mem in self._short_term:
                try:
                    mem_time = datetime.fromisoformat(mem.timestamp)
                    if mem_time.tzinfo is None:
                        mem_time = mem_time.replace(tzinfo=timezone.utc)
                    age_hours = (now - mem_time).total_seconds() / 3600.0
                except (ValueError, TypeError):
                    age_hours = 0.0

                # Keep if: recent enough, or high reward
                if age_hours < FORGETTING_AGE_HOURS or mem.reward >= LONG_TERM_PROMOTION_REWARD:
                    kept.append(mem)
            self._short_term = kept
            stats["pruned_short_term"] = before_count - len(kept)

        # ── 2. Forgetting: prune old, low-value long-term memories ────────
        pruned_lt = await storage.prune_mapl_memories(
            max_age_hours=FORGETTING_AGE_HOURS * 3,  # 90 days for long-term
            min_reward=0.0,
        )
        stats["pruned_long_term"] = pruned_lt

        # ── 3. Clustering / Summarization ─────────────────────────────────
        # Group remaining long-term memories by game_type and keep
        # only the top-N per type to prevent unbounded growth.
        all_lt = await storage.get_mapl_memories(limit=5000)
        type_groups: dict[str, list[dict]] = defaultdict(list)
        for doc in all_lt:
            gt = doc.get("state", {}).get("game_type", "unknown")
            type_groups[gt].append(doc)

        max_per_type = 50
        for gt, group in type_groups.items():
            if len(group) > max_per_type:
                # Sort by reward desc, keep top N
                group.sort(key=lambda d: d.get("reward", 0), reverse=True)
                to_remove = group[max_per_type:]
                for doc in to_remove:
                    mid = doc.get("memory_id", "")
                    if mid:
                        await storage.delete_mapl_memory(mid)
                        stats["clustered"] += 1

        self._last_optimization = now.isoformat()
        logger.info("MAPL optimization complete: %s", stats)
        return stats

    # ── Statistics ─────────────────────────────────────────────────────────

    async def get_stats(self, storage: "StorageManager") -> dict[str, Any]:
        """Return MAPL subsystem statistics."""
        lt_count = await storage.count_mapl_memories()

        # Game type distribution in long-term memory
        all_lt = await storage.get_mapl_memories(limit=5000)
        type_counter: Counter[str] = Counter()
        total_reward = 0.0
        for doc in all_lt:
            gt = doc.get("state", {}).get("game_type", "unknown")
            type_counter[gt] += 1
            total_reward += doc.get("reward", 0.0)

        async with self._lock:
            st_count = len(self._short_term)

        total = st_count + lt_count
        avg_reward = (total_reward / lt_count) if lt_count > 0 else self._mean_reward

        return {
            "short_term_count": st_count,
            "long_term_count": lt_count,
            "total_memories": total,
            "avg_reward": round(avg_reward, 3),
            "top_game_types": [
                {"game_type": gt, "count": c}
                for gt, c in type_counter.most_common(10)
            ],
            "last_optimization": self._last_optimization,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

mapl_service = MAPLService()
