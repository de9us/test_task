import json

import pytest
from faststream.message import AckStatus
from faststream.rabbit import TestRabbitBroker
from faststream.rabbit.message import RabbitMessage as RabbitMessageClass

from payment_service.messaging import EVENTS_EXCHANGE, MAIN_QUEUE
from payment_service.worker import broker


def capture_rejections(monkeypatch):
    rejected = []
    original_reject = RabbitMessageClass.reject

    async def spy_reject(self, *args, **kwargs):
        await original_reject(self, *args, **kwargs)
        rejected.append(self)

    monkeypatch.setattr(RabbitMessageClass, "reject", spy_reject)
    return rejected


@pytest.mark.asyncio
async def test_worker_rejects_non_mapping_payload(monkeypatch):
    rejected = capture_rejections(monkeypatch)

    async with TestRabbitBroker(broker) as test_broker:
        await test_broker.publish(
            ["not", "an", "object"],
            queue=MAIN_QUEUE,
            exchange=EVENTS_EXCHANGE,
        )

    assert len(rejected) == 1
    assert rejected[0].committed is AckStatus.REJECTED


@pytest.mark.asyncio
async def test_worker_rejects_malformed_json(monkeypatch):
    rejected = capture_rejections(monkeypatch)

    async with TestRabbitBroker(broker) as test_broker:
        with pytest.raises(json.JSONDecodeError):
            await test_broker.publish(
                b"{broken",
                queue=MAIN_QUEUE,
                exchange=EVENTS_EXCHANGE,
                content_type="application/json",
            )

    assert len(rejected) == 1
    assert rejected[0].committed is AckStatus.REJECTED
