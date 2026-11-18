from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from payment_service.config import Settings
from payment_service.models import Payment, PaymentStatus
from payment_service import processing


class FakeSession:
    def __init__(self, payment: Payment):
        self.payment = payment

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def begin(self):
        return self

    async def get(self, _model, _id, *, with_for_update=False):
        return self.payment

    def expunge(self, _record):
        pass


class FakeSessions:
    def __init__(self, payment):
        self.payment = payment

    def __call__(self):
        return FakeSession(self.payment)


def settings():
    return Settings(
        database_url="postgresql+asyncpg://local/local",
        rabbitmq_url="amqp://local/",
        api_key="a" * 20,
        webhook_signing_secret="b" * 20,
        gateway_delay_min_seconds=0,
        gateway_delay_max_seconds=0,
    )


def make_payment():
    return Payment(
        id=uuid4(), amount=Decimal("42.00"), currency="RUB", description="order",
        metadata_={}, status="pending", webhook_url="https://example.com/hook",
        webhook_attempts=0, idempotency_key="k", request_hash="a" * 64,
    )


@pytest.mark.asyncio
async def test_webhook_failure_does_not_recharge_or_revert_payment(monkeypatch):
    payment = make_payment()
    sessions = FakeSessions(payment)
    charge = AsyncMock(return_value=PaymentStatus.SUCCEEDED)
    webhook = AsyncMock(side_effect=RuntimeError("downstream unavailable"))
    monkeypatch.setattr(processing, "simulate_charge", charge)
    monkeypatch.setattr(processing, "post_webhook", webhook)

    event_id = uuid4()
    with pytest.raises(RuntimeError, match="downstream"):
        await processing.process_and_notify(payment.id, event_id, 1, sessions, settings())

    assert payment.status == "succeeded"
    assert payment.processed_at is not None
    assert payment.webhook_attempts == 1
    assert payment.webhook_delivered_at is None
    assert payment.last_webhook_error == "downstream unavailable"

    webhook.side_effect = None
    await processing.process_and_notify(payment.id, event_id, 2, sessions, settings())
    assert payment.status == "succeeded"
    assert payment.webhook_attempts == 2
    assert payment.webhook_delivered_at is not None
    assert payment.last_webhook_error is None
    assert charge.await_count == 1
    assert webhook.await_count == 2

    # Subsequent duplicate delivery MUST NOT invoke gateway or webhook again.
    await processing.process_and_notify(payment.id, event_id, 3, sessions, settings())
    assert charge.await_count == 1
    assert webhook.await_count == 2


@pytest.mark.asyncio
async def test_failed_payments_get_webhook_too(monkeypatch):
    payment = make_payment()
    charge = AsyncMock(return_value=PaymentStatus.FAILED)
    webhook = AsyncMock()
    monkeypatch.setattr(processing, "simulate_charge", charge)
    monkeypatch.setattr(processing, "post_webhook", webhook)

    await processing.process_and_notify(payment.id, uuid4(), 1, FakeSessions(payment), settings())
    assert payment.status == "failed"
    assert payment.webhook_delivered_at is not None
    assert webhook.await_count == 1
