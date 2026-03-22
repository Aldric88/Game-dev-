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

    async def connect(self) -> None:
        try:
            kwargs: dict = {"serverSelectionTimeoutMS": 3000}
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
