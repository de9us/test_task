from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payment_service.config import Settings
from payment_service.gateway import simulate_charge
from payment_service.models import Payment, PaymentStatus
from payment_service.webhooks import post_webhook


async def finalize_if_pending(
    payment_id: UUID, sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    async with sessions() as session, session.begin():
        payment = await session.get(Payment, payment_id, with_for_update=True)
        if payment is None:
            raise ValueError(f"unknown payment_id={payment_id}")
        if payment.status != PaymentStatus.PENDING.value:
            return
        outcome = await simulate_charge(payment_id, settings)
        payment.status = outcome.value
        payment.processed_at = datetime.now(UTC)


async def process_and_notify(
    payment_id: UUID,
    event_id: UUID,
    attempt: int,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await finalize_if_pending(payment_id, sessions, settings)

    async with sessions() as session:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise ValueError(f"unknown payment_id={payment_id}")
        if payment.webhook_delivered_at is not None:
            return
        session.expunge(payment)

    try:
        await post_webhook(payment, event_id, settings)
    except Exception as exc:
        async with sessions() as session, session.begin():
            locked = await session.get(Payment, payment_id, with_for_update=True)
            if locked is not None and locked.webhook_delivered_at is None:
                locked.webhook_attempts = max(locked.webhook_attempts, attempt)
                locked.last_webhook_error = str(exc)[:2000]
        raise
    else:
        async with sessions() as session, session.begin():
            locked = await session.get(Payment, payment_id, with_for_update=True)
            if locked is not None and locked.webhook_delivered_at is None:
                locked.webhook_attempts = max(locked.webhook_attempts, attempt)
                locked.webhook_delivered_at = datetime.now(UTC)
                locked.last_webhook_error = None
