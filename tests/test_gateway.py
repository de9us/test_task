from uuid import uuid4

import pytest

from payment_service.config import Settings
from payment_service.gateway import simulate_charge
from payment_service.models import PaymentStatus


def settings(**overrides):
    data = dict(
        database_url="postgresql+asyncpg://local/local",
        rabbitmq_url="amqp://local/",
        api_key="a" * 20,
        webhook_signing_secret="b" * 20,
        gateway_delay_min_seconds=0,
        gateway_delay_max_seconds=0,
    )
    data.update(overrides)
    return Settings(**data)


@pytest.mark.asyncio
async def test_gateway_result_stable_for_redelivery():
    payment_id = uuid4()
    cfg = settings()
    assert await simulate_charge(payment_id, cfg) == await simulate_charge(payment_id, cfg)


@pytest.mark.asyncio
async def test_gateway_rate_boundaries():
    payment_id = uuid4()
    assert await simulate_charge(payment_id, settings(gateway_success_rate=1)) == PaymentStatus.SUCCEEDED
    assert await simulate_charge(payment_id, settings(gateway_success_rate=0)) == PaymentStatus.FAILED


def test_settings_reject_reversed_delays():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        settings(gateway_delay_min_seconds=3, gateway_delay_max_seconds=2)
