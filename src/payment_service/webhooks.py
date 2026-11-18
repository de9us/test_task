import hashlib
import hmac
import json
from typing import Any
from uuid import UUID

import httpx

from payment_service.config import Settings
from payment_service.models import Payment


def build_webhook_body(payment: Payment, event_id: UUID) -> bytes:
    payload: dict[str, Any] = {
        "event_id": str(event_id),
        "event_type": "payment.processed",
        "payment_id": str(payment.id),
        "status": payment.status,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def calculate_signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def post_webhook(
    payment: Payment, event_id: UUID, settings: Settings, *, client: httpx.AsyncClient | None = None
) -> None:
    body = build_webhook_body(payment, event_id)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event-ID": str(event_id),
        "X-Webhook-Signature": calculate_signature(settings.webhook_signing_secret, body),
    }
    if client is not None:
        response = await client.post(payment.webhook_url, content=body, headers=headers)
        response.raise_for_status()
    else:
        async with httpx.AsyncClient(
            timeout=settings.webhook_timeout_seconds, follow_redirects=False, trust_env=False
        ) as new_client:
            response = await new_client.post(payment.webhook_url, content=body, headers=headers)
            response.raise_for_status()
