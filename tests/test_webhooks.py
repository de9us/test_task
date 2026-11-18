import hashlib
import hmac
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from payment_service.config import Settings
from payment_service.models import Payment
from payment_service.webhooks import build_webhook_body, calculate_signature, post_webhook


def payment():
    return Payment(
        id=uuid4(),
        amount=Decimal("17.50"),
        currency="EUR",
        status="succeeded",
        description="demo",
        idempotency_key="key",
        request_hash="a" * 64,
        metadata_={},
        webhook_url="https://receiver.example/callback",
        processed_at=datetime.now(UTC),
    )


def settings():
    return Settings(
        database_url="postgresql+asyncpg://local/local",
        rabbitmq_url="amqp://local/",
        api_key="a" * 20,
        webhook_signing_secret="secret-for-webhook-testing",
    )


@pytest.mark.asyncio
async def test_webhook_has_stable_id_and_valid_signature():
    p = payment()
    event_id = uuid4()
    captured = {}

    def receiver(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(receiver)) as client:
        await post_webhook(p, event_id, settings(), client=client)
    request = captured["request"]
    expected = "sha256=" + hmac.new(
        settings().webhook_signing_secret.encode(), request.content, hashlib.sha256
    ).hexdigest()
    assert request.headers["X-Webhook-Event-ID"] == str(event_id)
    assert request.headers["X-Webhook-Signature"] == expected
    data = json.loads(request.content)
    assert data["amount"] == "17.50"
    assert data["payment_id"] == str(p.id)
    assert build_webhook_body(p, event_id) == request.content
    assert calculate_signature(settings().webhook_signing_secret, request.content) == expected


@pytest.mark.asyncio
async def test_webhook_non_2xx_is_failure():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await post_webhook(payment(), uuid4(), settings(), client=client)
