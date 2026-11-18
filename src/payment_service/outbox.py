import asyncio
import logging
from datetime import UTC, datetime, timedelta

from faststream.rabbit import RabbitBroker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.config import get_settings
from payment_service.db import session_factory
from payment_service.messaging import declare_topology, make_broker, publish_payment_event
from payment_service.models import OutboxEvent

logger = logging.getLogger(__name__)


def backoff_seconds(failures: int) -> int:
    return min(2 ** min(failures, 6), 60)


async def publish_next(
    broker: RabbitBroker, sessions: async_sessionmaker[AsyncSession]
) -> bool:
    async with sessions() as session, session.begin():
        event = await session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.published_at.is_(None),
                OutboxEvent.next_attempt_at <= datetime.now(UTC),
            )
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            return False
        try:
            await publish_payment_event(
                broker, event_id=event.id, payment_id=event.payment_id
            )
        except Exception as exc:
            event.publish_attempts += 1
            event.last_error = str(exc)[:2000]
            event.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=backoff_seconds(event.publish_attempts)
            )
            logger.exception("outbox_publish_failed event_id=%s", event.id)
        else:
            event.published_at = datetime.now(UTC)
            event.publish_attempts += 1
            event.last_error = None
            logger.info("outbox_published event_id=%s payment_id=%s", event.id, event.payment_id)
        return True


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    await declare_topology(settings)
    async with make_broker(settings) as broker:
        while True:
            try:
                did_work = await publish_next(broker, session_factory)
                if not did_work:
                    await asyncio.sleep(settings.outbox_poll_interval_seconds)
            except Exception:
                # If the database disconnects, never lose an event. Restart the next poll.
                logger.exception("outbox_loop_failed")
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
