import asyncio
import hashlib
from uuid import UUID

from payment_service.config import Settings
from payment_service.models import PaymentStatus


async def simulate_charge(payment_id: UUID, settings: Settings) -> PaymentStatus:
    digest = hashlib.sha256(payment_id.bytes).digest()
    n = int.from_bytes(digest[:8], "big") / 2**64
    duration = settings.gateway_delay_min_seconds + (
        settings.gateway_delay_max_seconds - settings.gateway_delay_min_seconds
    ) * (int.from_bytes(digest[8:16], "big") / 2**64)
    await asyncio.sleep(duration)
    return PaymentStatus.SUCCEEDED if n < settings.gateway_success_rate else PaymentStatus.FAILED
