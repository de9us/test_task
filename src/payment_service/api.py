import secrets
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from payment_service.config import get_settings
from payment_service.db import get_session
from payment_service.models import Payment
from payment_service.payments import IdempotencyConflict, create_payment
from payment_service.schemas import PaymentAccepted, PaymentCreate, PaymentDetails

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def authorize(api_key: str | None = Depends(api_key_header)) -> None:
    expected = get_settings().api_key
    if api_key is None or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


app = FastAPI(
    title="Async Payment Processing Service",
    version="1.0.0",
    description="Idempotent payments with transactional outbox and webhook notifications.",
    docs_url=None, redoc_url=None, openapi_url=None,
)


@app.post(
    "/api/v1/payments",
    response_model=PaymentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Payments"],
    dependencies=[Depends(authorize)],
)
async def post_payment(
    body: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=255),
    session: AsyncSession = Depends(get_session),
) -> PaymentAccepted:
    if not idempotency_key.strip():
        raise HTTPException(status_code=422, detail="Idempotency-Key must not be blank")
    try:
        return await create_payment(session, body=body, idempotency_key=idempotency_key)
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used with a different payload",
        ) from exc


@app.get(
    "/api/v1/payments/{payment_id}",
    response_model=PaymentDetails,
    tags=["Payments"],
    dependencies=[Depends(authorize)],
)
async def get_payment(
    payment_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PaymentDetails:
    payment = await session.scalar(select(Payment).where(Payment.id == payment_id))
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return PaymentDetails.from_record(payment)


@app.get("/healthz", include_in_schema=False, dependencies=[Depends(authorize)])
async def healthcheck(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
