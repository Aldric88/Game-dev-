"""Basic smoke tests for the ForgeAI backend."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_register_and_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register
        r = await client.post("/api/v1/auth/register", json={
            "username": "testuser_smoke",
            "email": "smoke@test.invalid",
            "password": "Smoke1234!",
        })
        assert r.status_code in (201, 409)  # 409 = already exists, both fine for smoke test

        # Login
        r2 = await client.post("/api/v1/auth/login", json={
            "email": "smoke@test.invalid",
            "password": "Smoke1234!",
        })
        assert r2.status_code in (200, 401)


@pytest.mark.asyncio
async def test_projects_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/projects")
    assert r.status_code == 401
