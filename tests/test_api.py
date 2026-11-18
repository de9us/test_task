import httpx
import pytest

from payment_service.api import app
from payment_service.config import get_settings


@pytest.mark.asyncio
async def test_api_rejects_missing_key():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/api/v1/payments/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_rejects_wrong_key():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get(
            "/api/v1/payments/00000000-0000-0000-0000-000000000001",
            headers={"X-API-Key": "wrong"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_validation_prevents_db_access():
    body = {"amount": "-10", "currency": "EUR", "description": "bad", "webhook_url": "https://example.com"}
    headers = {"X-API-Key": get_settings().api_key, "Idempotency-Key": "unique-1"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/api/v1/payments", json=body, headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_idempotency_key():
    body = {"amount": "10", "currency": "EUR", "description": "ok", "webhook_url": "https://example.com"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post(
            "/api/v1/payments", json=body, headers={"X-API-Key": get_settings().api_key}
        )
    assert response.status_code == 422
