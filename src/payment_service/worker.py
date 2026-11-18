import asyncio
import logging
from typing import Any

from faststream import AckPolicy, FastStream
from faststream.rabbit import RabbitQueue
from faststream.rabbit.annotations import RabbitMessage
from pydantic import ValidationError

from payment_service.config import get_settings
from payment_service.db import session_factory
from payment_service.messaging import (
    DLX_NAME,
    EVENTS_EXCHANGE,
    MAIN_QUEUE,
    declare_topology,
    make_broker,
    publish_retry,
)
from payment_service.processing import process_and_notify
from payment_service.schemas import PaymentEvent

logger = logging.getLogger(__name__)
settings = get_settings()
broker = make_broker(settings, prefetch_count=1)
app = FastStream(broker)


@app.on_startup
async def prepare_topology() -> None:
    await declare_topology(settings)


@broker.subscriber(
    RabbitQueue(
        MAIN_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_NAME,
            "x-dead-letter-routing-key": "payments.dead",
        },
    ),
    EVENTS_EXCHANGE,
    ack_policy=AckPolicy.REJECT_ON_ERROR,
)
async def handle_payment(payload: Any, message: RabbitMessage) -> None:
    try:
        event = PaymentEvent.model_validate(payload)
    except ValidationError:
        logger.exception("invalid_payment_event_rejected")
        await message.reject()  # RabbitMQ sends poison messages to payments.dlq.
        return

    try:
        await process_and_notify(
            event.payment_id, event.event_id, event.attempt, session_factory, settings
        )
    except Exception:
        logger.exception(
            "payment_processing_attempt_failed payment_id=%s attempt=%s",
            event.payment_id,
            event.attempt,
        )
        if event.attempt == 3:
            await message.reject()
        else:
            try:
                await publish_retry(broker, event)
            except Exception:
                logger.exception("retry_publish_failed_requeuing_original")
                await message.nack()
            else:
                await message.ack()
    else:
        await message.ack()
        logger.info("payment_handled payment_id=%s", event.payment_id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
