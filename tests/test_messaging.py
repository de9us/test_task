from uuid import uuid4

import pytest

from payment_service.messaging import publish_payment_event, publish_retry
from payment_service.outbox import backoff_seconds
from payment_service.schemas import PaymentEvent


class FakeBroker:
    def __init__(self, result=True):
        self.calls = []
        self.result = result

    async def publish(self, body, **kwargs):
        self.calls.append((body, kwargs))
        return self.result


@pytest.mark.asyncio
async def test_outbox_publishes_persistent_message_with_id():
    broker = FakeBroker()
    event_id, payment_id = uuid4(), uuid4()
    await publish_payment_event(broker, event_id=event_id, payment_id=payment_id)
    body, opts = broker.calls[0]
    assert body == {"event_id": str(event_id), "payment_id": str(payment_id), "attempt": 1}
    assert opts["queue"] == "payments.new"
    assert opts["persist"] and opts["mandatory"]
    assert opts["message_id"] == str(event_id)


@pytest.mark.asyncio
async def test_retry_increments_attempt_and_uses_delayed_queue():
    broker = FakeBroker()
    e = PaymentEvent(event_id=uuid4(), payment_id=uuid4(), attempt=1)
    await publish_retry(broker, e)
    assert broker.calls[0][0]["attempt"] == 2
    assert broker.calls[0][1]["queue"] == "payments.retry.1"
    assert e.attempt == 1


@pytest.mark.asyncio
async def test_negative_broker_confirmation_is_error():
    broker = FakeBroker(result=False)
    with pytest.raises(RuntimeError, match="negatively acknowledged"):
        await publish_payment_event(broker, event_id=uuid4(), payment_id=uuid4())


@pytest.mark.asyncio
async def test_no_fourth_attempt():
    with pytest.raises(ValueError):
        await publish_retry(
            FakeBroker(), PaymentEvent(event_id=uuid4(), payment_id=uuid4(), attempt=3)
        )


def test_outbox_retries_backoff_with_cap():
    assert [backoff_seconds(i) for i in (1, 2, 3, 20)] == [2, 4, 8, 60]
