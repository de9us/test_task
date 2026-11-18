from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.models import OutboxEvent, Payment, PaymentStatus
from payment_service.schemas import PaymentAccepted, PaymentCreate


class IdempotencyConflict(Exception):
    """Same idempotency key has been used for a different request."""


async def create_payment(
    session: AsyncSession, *, body: PaymentCreate, idempotency_key: str
) -> PaymentAccepted:
    payment_id = uuid4()
    fingerprint = body.fingerprint()

    async with session.begin():
        statement = (
            insert(Payment)
            .values(
                id=payment_id,
                amount=body.amount,
                currency=body.currency.value,
                description=body.description,
                metadata_=body.metadata,
                status=PaymentStatus.PENDING.value,
                idempotency_key=idempotency_key,
                request_hash=fingerprint,
                webhook_url=str(body.webhook_url),
                webhook_attempts=0,
            )
            .on_conflict_do_nothing(index_elements=[Payment.idempotency_key])
            .returning(Payment.id)
        )
        inserted_id = await session.scalar(statement)

        if inserted_id is not None:
            session.add(
                OutboxEvent(
                    id=uuid4(),
                    payment_id=payment_id,
                    event_type="payment.created",
                    payload={"payment_id": str(payment_id)},
                )
            )
            await session.flush()
            payment = await session.get(Payment, payment_id)
        else:
            payment = await session.scalar(
                select(Payment).where(Payment.idempotency_key == idempotency_key)
            )
            if payment is None:
                raise RuntimeError("idempotency winner is unexpectedly missing")
            if payment.request_hash != fingerprint:
                raise IdempotencyConflict

        assert payment is not None
        response = PaymentAccepted(
            payment_id=payment.id,
            status=PaymentStatus(payment.status),
            created_at=payment.created_at or datetime.now(UTC),
        )
    return response
