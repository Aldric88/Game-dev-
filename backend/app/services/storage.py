"""MongoDB storage service with in-memory fallback."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings


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
            client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
            await client.admin.command("ping")
            self._mongo_client = client
            self._mongo_db = client[settings.mongodb_db_name]
            self.mode = "mongo"
        except Exception:
            if settings.allow_inmemory_fallback:
                self.mode = "memory"
            else:
                raise

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
        return project

    async def delete_project(self, project_id: str) -> bool:
        if self.mode == "mongo":
            result = await self._mongo_projects.delete_one({"project_id": project_id})
            return result.deleted_count > 0
        async with self._lock:
            if project_id in self._memory_projects:
                del self._memory_projects[project_id]
                return True
        return False
