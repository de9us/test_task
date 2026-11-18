import hashlib
import hmac
import json
import logging
from collections import deque
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from payment_service.config import get_settings

logger = logging.getLogger(__name__)
app = FastAPI(title="Development webhook sink", docs_url=None, redoc_url=None)
_received: deque[dict[str, Any]] = deque(maxlen=100)


@app.post("/webhook", status_code=204)
async def receive(request: Request) -> Response:
    body = await request.body()
    expected = "sha256=" + hmac.new(
        get_settings().webhook_signing_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    provided = request.headers.get("X-Webhook-Signature", "")
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(401, "Bad webhook signature")
    event = json.loads(body)
    _received.append(event)
    logger.info("webhook_received payment_id=%s status=%s", event["payment_id"], event["status"])
    return Response(status_code=204)


@app.post("/always-fail", status_code=503)
async def always_fail() -> dict[str, str]:
    raise HTTPException(503, "Simulated downstream outage")


@app.get("/events")
async def events() -> list[dict[str, Any]]:
    return list(_received)
