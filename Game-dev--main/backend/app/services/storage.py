"""MongoDB storage service with in-memory fallback."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

_storage_logger = logging.getLogger(__name__)


class StorageManager:
    def __init__(self) -> None:
        self.mode: str = "memory"
        self._mongo_client: AsyncIOMotorClient | None = None
        self._mongo_db: AsyncIOMotorDatabase | None = None
        self._lock = asyncio.Lock()
        self._memory_users: dict[str, dict] = {}
        self._memory_projects: dict[str, dict] = {}
        self._memory_ml_examples: list[dict] = []
        self._memory_mapl: list[dict] = []

    async def connect(self) -> None:
        try:
            kwargs: dict = {"serverSelectionTimeoutMS": 10000}
            # On macOS the system Python doesn't use the OS certificate store.
            # Pass certifi's CA bundle so TLS works for Atlas (mongodb+srv://).
            if settings.mongodb_uri.startswith("mongodb+srv://") or "tls=true" in settings.mongodb_uri.lower():
                try:
                    import certifi
                    kwargs["tlsCAFile"] = certifi.where()
                except ImportError:
                    pass
            client = AsyncIOMotorClient(settings.mongodb_uri, **kwargs)
            await client.admin.command("ping")
            self._mongo_client = client
            self._mongo_db = client[settings.mongodb_db_name]
            self.mode = "mongo"
            await self._ensure_indexes()
        except Exception:
            if settings.allow_inmemory_fallback:
                self.mode = "memory"
            else:
                raise

    async def _ensure_indexes(self) -> None:
        """Create indexes required for efficient queries. Safe to call repeatedly."""
        try:
            await self._mongo_users.create_index("email", unique=True, background=True)
            await self._mongo_users.create_index("username", unique=True, background=True)
            await self._mongo_users.create_index("user_id", unique=True, background=True)
            await self._mongo_projects.create_index("project_id", unique=True, background=True)
            await self._mongo_projects.create_index("user_id", background=True)
            await self._mongo_projects.create_index(
                [("user_id", 1), ("updated_at", -1)], background=True
            )
            await self._mongo_projects.create_index("is_public", background=True)
            await self._mongo_projects.create_index(
                [("is_public", 1), ("plays", -1)], background=True
            )
            await self._mongo_projects.create_index(
                [("is_public", 1), ("likes", -1)], background=True
            )
            # MAPL memory indexes
            await self._mongo_mapl_memories.create_index("memory_id", unique=True, background=True)
            await self._mongo_mapl_memories.create_index("user_id", background=True)
            await self._mongo_mapl_memories.create_index(
                [("state.game_type", 1), ("reward", -1)], background=True
            )
            await self._mongo_mapl_memories.create_index("timestamp", background=True)
            _storage_logger.info("MongoDB indexes ensured.")
        except Exception as exc:
            _storage_logger.warning("Could not create MongoDB indexes: %s", exc)

    async def close(self) -> None:
        if self._mongo_client:
            self._mongo_client.close()

    @property
    def _users_collection_name(self) -> str:
        return "users"

    @property
    def _projects_collection_name(self) -> str:
        return "projects"

    @property
    def _mongo_users(self):
        if self._mongo_db is None:
            raise RuntimeError("MongoDB database is not initialized")
        return self._mongo_db[self._users_collection_name]

    @property
    def _mongo_projects(self):
        if self._mongo_db is None:
            raise RuntimeError("MongoDB database is not initialized")
        return self._mongo_db[self._projects_collection_name]

    @property
    def _mongo_ml_examples(self):
        if self._mongo_db is None:
            raise RuntimeError("MongoDB database is not initialized")
        return self._mongo_db["ml_training_data"]

    @property
    def _mongo_mapl_memories(self):
        if self._mongo_db is None:
            raise RuntimeError("MongoDB database is not initialized")
        return self._mongo_db["mapl_memories"]

    @staticmethod
    def _normalize_doc(doc: dict) -> dict:
        doc = dict(doc)
        oid = doc.pop("_id", None)
        if oid and "user_id" not in doc and "project_id" not in doc:
            doc["id"] = str(oid)
        return doc

    # ── Stats ──────────────────────────────────────────────────────────────

    async def count_users(self) -> int:
        if self.mode == "mongo":
            return await self._mongo_users.count_documents({})
        return len(self._memory_users)

    async def count_projects(self) -> int:
        if self.mode == "mongo":
            return await self._mongo_projects.count_documents({})
        return len(self._memory_projects)

    # ── Users ──────────────────────────────────────────────────────────────

    async def create_user(self, data: dict[str, Any]) -> dict[str, Any]:
        user_id = str(uuid4())
        data = {**data, "user_id": user_id}
        if self.mode == "mongo":
            result = await self._mongo_users.insert_one(data)
            data["_id"] = result.inserted_id
            return self._normalize_doc(data)
        async with self._lock:
            self._memory_users[user_id] = data
        return data

    async def update_user_usage(self, user_id: str, api_calls: int = 1, ai_tokens: int = 0) -> None:
        if self.mode == "mongo":
            await self._mongo_users.update_one(
                {"user_id": user_id},
                {"$inc": {"usage_stats.api_calls": api_calls, "usage_stats.ai_tokens_used": ai_tokens}},
            )
        else:
            async with self._lock:
                user = self._memory_users.get(user_id, {})
                stats = user.setdefault("usage_stats", {})
                stats["api_calls"] = stats.get("api_calls", 0) + api_calls
                stats["ai_tokens_used"] = stats.get("ai_tokens_used", 0) + ai_tokens

    async def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        if self.mode == "mongo":
            doc = await self._mongo_users.find_one({"email": email})
            return self._normalize_doc(doc) if doc else None
        for u in self._memory_users.values():
            if u.get("email") == email:
                return u
        return None

    async def find_user_by_username(self, username: str) -> dict[str, Any] | None:
        if self.mode == "mongo":
            doc = await self._mongo_users.find_one({"username": username})
            return self._normalize_doc(doc) if doc else None
        for u in self._memory_users.values():
            if u.get("username") == username:
                return u
        return None

    async def find_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        if self.mode == "mongo":
            doc = await self._mongo_users.find_one({"user_id": user_id})
            return self._normalize_doc(doc) if doc else None
        return self._memory_users.get(user_id)

    async def update_user(self, user_id: str, update: dict[str, Any]) -> dict[str, Any] | None:
        if self.mode == "mongo":
            await self._mongo_users.update_one({"user_id": user_id}, {"$set": update})
            return await self.find_user_by_id(user_id)
        async with self._lock:
            user = self._memory_users.get(user_id)
            if user is None:
                return None
            user.update(update)
            # Return a shallow copy *inside* the lock so the caller receives a
            # snapshot that a concurrent writer cannot mutate underneath it.
            return dict(user)

    async def delete_user(self, user_id: str) -> bool:
        if self.mode == "mongo":
            result = await self._mongo_users.delete_one({"user_id": user_id})
            return result.deleted_count > 0
        async with self._lock:
            if user_id in self._memory_users:
                del self._memory_users[user_id]
                return True
        return False

    async def deduct_credit(self, user_id: str) -> bool:
        """Atomically deduct one credit. Returns False if no credits remain."""
        if self.mode == "mongo":
            result = await self._mongo_users.update_one(
                {"user_id": user_id, "credits": {"$gt": 0}},
                {"$inc": {"credits": -1, "credits_used_this_month": 1}},
            )
            return result.modified_count > 0
        async with self._lock:
            user = self._memory_users.get(user_id)
            if not user or user.get("credits", 0) <= 0:
                return False
            user["credits"] = user.get("credits", 0) - 1
            user["credits_used_this_month"] = user.get("credits_used_this_month", 0) + 1
        return True

    async def add_credits(self, user_id: str, amount: int) -> None:
        if self.mode == "mongo":
            await self._mongo_users.update_one(
                {"user_id": user_id},
                {"$inc": {"credits": amount}},
            )
        else:
            async with self._lock:
                user = self._memory_users.get(user_id)
                if user:
                    user["credits"] = user.get("credits", 0) + amount

    async def reset_all_monthly_credits(self, plan_limits: dict[str, int]) -> None:
        """Reset credits for all users based on their plan (called monthly)."""
        if self.mode == "mongo":
            for plan, limit in plan_limits.items():
                if limit == -1:
                    continue
                await self._mongo_users.update_many(
                    {"plan": plan},
                    {"$set": {"credits": limit, "credits_used_this_month": 0}},
                )
        else:
            async with self._lock:
                for user in self._memory_users.values():
                    plan = user.get("plan", "free")
                    limit = plan_limits.get(plan, 10)
                    if limit == -1:
                        continue
                    user["credits"] = limit
                    user["credits_used_this_month"] = 0

    # ── Projects ───────────────────────────────────────────────────────────

    async def create_project(self, data: dict[str, Any]) -> dict[str, Any]:
        project_id = str(uuid4())
        data = {**data, "project_id": project_id}
        if self.mode == "mongo":
            result = await self._mongo_projects.insert_one(data)
            data["_id"] = result.inserted_id
            return self._normalize_doc(data)
        async with self._lock:
            self._memory_projects[project_id] = data
        return data

    async def list_projects(self, user_id: str) -> list[dict[str, Any]]:
        if self.mode == "mongo":
            cursor = self._mongo_projects.find({"user_id": user_id}).sort("updated_at", -1)
            docs = await cursor.to_list(length=200)
            return [self._normalize_doc(d) for d in docs]
        projects = [p for p in self._memory_projects.values() if p.get("user_id") == user_id]
        return sorted(projects, key=lambda p: p.get("updated_at", ""), reverse=True)

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        if self.mode == "mongo":
            doc = await self._mongo_projects.find_one({"project_id": project_id})
            return self._normalize_doc(doc) if doc else None
        return self._memory_projects.get(project_id)

    async def update_project(self, project_id: str, update: dict[str, Any]) -> dict[str, Any] | None:
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        if self.mode == "mongo":
            await self._mongo_projects.update_one(
                {"project_id": project_id}, {"$set": update}
            )
            return await self.get_project(project_id)
        async with self._lock:
            project = self._memory_projects.get(project_id)
            if project is None:
                return None
            project.update(update)
            # Return a shallow copy inside the lock — same reasoning as update_user.
            return dict(project)

    async def delete_project(self, project_id: str) -> bool:
        if self.mode == "mongo":
            result = await self._mongo_projects.delete_one({"project_id": project_id})
            return result.deleted_count > 0
        async with self._lock:
            if project_id in self._memory_projects:
                del self._memory_projects[project_id]
                return True
        return False

    async def list_public_projects(self, search: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """Return public projects sorted by plays descending, with optional text search."""
        if self.mode == "mongo":
            query: dict = {"is_public": True}
            if search:
                query["$or"] = [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"description": {"$regex": search, "$options": "i"}},
                ]
            cursor = self._mongo_projects.find(query).sort("plays", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
            return [self._normalize_doc(d) for d in docs]
        projects = [p for p in self._memory_projects.values() if p.get("is_public", False)]
        if search:
            s = search.lower()
            projects = [
                p for p in projects
                if s in p.get("name", "").lower() or s in p.get("description", "").lower()
            ]
        return sorted(projects, key=lambda p: p.get("plays", 0), reverse=True)[:limit]

    async def increment_plays(self, project_id: str) -> None:
        """Atomically increment the play counter for a public project."""
        if self.mode == "mongo":
            await self._mongo_projects.update_one(
                {"project_id": project_id},
                {"$inc": {"plays": 1}},
            )
        else:
            async with self._lock:
                project = self._memory_projects.get(project_id)
                if project:
                    project["plays"] = project.get("plays", 0) + 1

    async def toggle_like(self, project_id: str, user_id: str) -> dict[str, Any] | None:
        """Like or unlike a project. Returns {likes, liked} or None if not found."""
        if self.mode == "mongo":
            doc = await self._mongo_projects.find_one({"project_id": project_id})
            if not doc:
                return None
            already_liked = user_id in doc.get("liked_by", [])
            if already_liked:
                await self._mongo_projects.update_one(
                    {"project_id": project_id},
                    {"$pull": {"liked_by": user_id}, "$inc": {"likes": -1}},
                )
                return {"likes": max(0, doc.get("likes", 1) - 1), "liked": False}
            else:
                await self._mongo_projects.update_one(
                    {"project_id": project_id},
                    {"$addToSet": {"liked_by": user_id}, "$inc": {"likes": 1}},
                )
                return {"likes": doc.get("likes", 0) + 1, "liked": True}
        async with self._lock:
            project = self._memory_projects.get(project_id)
            if not project:
                return None
            liked_by = project.setdefault("liked_by", [])
            if user_id in liked_by:
                liked_by.remove(user_id)
                project["likes"] = max(0, project.get("likes", 1) - 1)
                return {"likes": project["likes"], "liked": False}
            liked_by.append(user_id)
            project["likes"] = project.get("likes", 0) + 1
            return {"likes": project["likes"], "liked": True}

    async def add_search_event(self, user_id: str, event: dict[str, Any]) -> None:
        """Append a search event to the user's history, keeping the last 50."""
        if self.mode == "mongo":
            await self._mongo_users.update_one(
                {"user_id": user_id},
                {"$push": {"search_history": {"$each": [event], "$slice": -50}}},
            )
        else:
            async with self._lock:
                user = self._memory_users.get(user_id)
                if user:
                    hist = user.setdefault("search_history", [])
                    hist.append(event)
                    user["search_history"] = hist[-50:]

    async def get_search_history(self, user_id: str) -> list[dict[str, Any]]:
        """Return the user's last 20 search events."""
        if self.mode == "mongo":
            doc = await self._mongo_users.find_one({"user_id": user_id}, {"search_history": 1})
            return (doc or {}).get("search_history", [])[-20:]
        user = self._memory_users.get(user_id, {})
        return user.get("search_history", [])[-20:]

    async def record_user_play(self, user_id: str, project_id: str, game_type: str) -> None:
        """Record a user playing a game, keeping last 50 entries."""
        event = {
            "project_id": project_id,
            "game_type": game_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self.mode == "mongo":
            await self._mongo_users.update_one(
                {"user_id": user_id},
                {"$push": {"play_history": {"$each": [event], "$slice": -50}}},
            )
        else:
            async with self._lock:
                user = self._memory_users.get(user_id)
                if user:
                    hist = user.setdefault("play_history", [])
                    hist.append(event)
                    user["play_history"] = hist[-50:]

    async def get_user_play_history(self, user_id: str) -> list[dict[str, Any]]:
        """Return the user's last 20 played games."""
        if self.mode == "mongo":
            doc = await self._mongo_users.find_one({"user_id": user_id}, {"play_history": 1})
            return (doc or {}).get("play_history", [])[-20:]
        user = self._memory_users.get(user_id, {})
        return user.get("play_history", [])[-20:]

    async def get_user_liked_project_ids(self, user_id: str) -> list[str]:
        """Return IDs of all public projects liked by this user."""
        if self.mode == "mongo":
            cursor = self._mongo_projects.find(
                {"is_public": True, "liked_by": user_id},
                {"project_id": 1},
            )
            docs = await cursor.to_list(length=500)
            return [d["project_id"] for d in docs]
        return [
            p["project_id"]
            for p in self._memory_projects.values()
            if p.get("is_public") and user_id in p.get("liked_by", [])
        ]

    # ── ML Training Data ──────────────────────────────────────────────────────

    async def add_ml_example(self, text: str, label: str, confidence: float = 1.0) -> None:
        """Save a user-generated training signal to the ml_training_data collection."""
        doc = {
            "text":       text,
            "label":      label,
            "confidence": confidence,
            "trained":    False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if self.mode == "mongo":
            await self._mongo_ml_examples.insert_one(doc)
        else:
            async with self._lock:
                self._memory_ml_examples.append(doc)

    async def count_pending_ml_examples(self) -> int:
        """Count untrained user examples accumulated since last retrain."""
        if self.mode == "mongo":
            return await self._mongo_ml_examples.count_documents({"trained": False})
        return sum(1 for e in self._memory_ml_examples if not e.get("trained"))

    async def get_all_ml_examples(self) -> list[dict[str, Any]]:
        """Return all user-contributed training examples."""
        if self.mode == "mongo":
            docs = await self._mongo_ml_examples.find({}, {"_id": 0}).to_list(length=10000)
            return docs
        return list(self._memory_ml_examples)

    async def mark_ml_examples_trained(self) -> None:
        """Mark all pending examples as trained after a successful retrain."""
        if self.mode == "mongo":
            await self._mongo_ml_examples.update_many(
                {"trained": False},
                {"$set": {"trained": True}},
            )
        else:
            async with self._lock:
                for e in self._memory_ml_examples:
                    e["trained"] = True

    # ── MAPL Memory ───────────────────────────────────────────────────────────

    async def add_mapl_memory(self, doc: dict[str, Any]) -> None:
        """Persist a MAPL experience memory to long-term storage."""
        if self.mode == "mongo":
            await self._mongo_mapl_memories.insert_one(doc)
        else:
            async with self._lock:
                self._memory_mapl.append(doc)

    async def get_mapl_memories(
        self,
        user_id: str = "",
        game_type: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Retrieve MAPL memories, optionally filtered by user or game type."""
        if self.mode == "mongo":
            query: dict[str, Any] = {}
            if user_id:
                query["user_id"] = user_id
            if game_type:
                query["state.game_type"] = game_type
            cursor = self._mongo_mapl_memories.find(
                query, {"_id": 0}
            ).sort("timestamp", -1).limit(limit)
            return await cursor.to_list(length=limit)
        # In-memory fallback
        results = self._memory_mapl
        if user_id:
            results = [m for m in results if m.get("user_id") == user_id]
        if game_type:
            results = [
                m for m in results
                if m.get("state", {}).get("game_type") == game_type
            ]
        return list(reversed(results[-limit:]))

    async def count_mapl_memories(self) -> int:
        """Count total long-term MAPL memories."""
        if self.mode == "mongo":
            return await self._mongo_mapl_memories.count_documents({})
        return len(self._memory_mapl)

    async def delete_mapl_memory(self, memory_id: str) -> bool:
        """Delete a single MAPL memory by ID."""
        if self.mode == "mongo":
            result = await self._mongo_mapl_memories.delete_one({"memory_id": memory_id})
            return result.deleted_count > 0
        async with self._lock:
            before = len(self._memory_mapl)
            self._memory_mapl = [
                m for m in self._memory_mapl if m.get("memory_id") != memory_id
            ]
            return len(self._memory_mapl) < before

    async def prune_mapl_memories(
        self,
        max_age_hours: float = 2160,
        min_reward: float = 0.0,
    ) -> int:
        """Remove old, low-reward long-term memories. Returns count pruned."""
        from datetime import datetime, timezone
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        pruned = 0

        if self.mode == "mongo":
            cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
            result = await self._mongo_mapl_memories.delete_many({
                "timestamp": {"$lt": cutoff_iso},
                "reward": {"$lt": min_reward},
            })
            pruned = result.deleted_count
        else:
            async with self._lock:
                before = len(self._memory_mapl)
                kept: list[dict] = []
                for m in self._memory_mapl:
                    ts_str = m.get("timestamp", "")
                    try:
                        ts = datetime.fromisoformat(ts_str).timestamp()
                    except (ValueError, TypeError):
                        ts = cutoff + 1  # keep if unparseable
                    if ts >= cutoff or m.get("reward", 0) >= min_reward:
                        kept.append(m)
                self._memory_mapl = kept
                pruned = before - len(kept)

        return pruned
