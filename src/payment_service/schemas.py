import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from payment_service.models import Currency, Payment, PaymentStatus


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    description: str = Field(min_length=1, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must be valid JSON") from exc
        if len(encoded.encode("utf-8")) > 16_384:
            raise ValueError("metadata must be <= 16 KiB")
        return value

    @field_validator("amount")
    @classmethod
    def check_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("amount must be finite")
        return value.quantize(Decimal("0.01"))

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PaymentAccepted(BaseModel):
    payment_id: UUID
    status: PaymentStatus
    created_at: datetime


class PaymentDetails(BaseModel):
    payment_id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: PaymentStatus
    webhook_url: HttpUrl
    idempotency_key: str
    webhook_attempts: int
    last_webhook_error: str | None
    webhook_delivered_at: datetime | None
    created_at: datetime
    processed_at: datetime | None

    @classmethod
    def from_record(cls, payment: Payment) -> "PaymentDetails":
        return cls(
            payment_id=payment.id,
            amount=payment.amount,
            currency=Currency(payment.currency),
            description=payment.description,
            metadata=payment.metadata_,
            status=PaymentStatus(payment.status),
            webhook_url=payment.webhook_url,
            idempotency_key=payment.idempotency_key,
            webhook_attempts=payment.webhook_attempts,
            last_webhook_error=payment.last_webhook_error,
            webhook_delivered_at=payment.webhook_delivered_at,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )


class PaymentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    payment_id: UUID
    attempt: int = Field(default=1, ge=1, le=3)
