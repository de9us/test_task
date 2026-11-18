"""End-to-end smoke test against an already running Docker Compose stack.

Runs HTTP idempotency/conflict checks, polls payment completion and verifies the
local signed webhook receiver accepted the event. No extra Python dependencies.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

API = os.getenv("SMOKE_API_URL", "http://localhost:8000")
SINK = os.getenv("SMOKE_SINK_URL", "http://localhost:9001")
KEY = os.getenv("API_KEY", "replace-this-with-a-long-random-api-key")


def request(method, url, *, headers=None, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, method=method, data=body, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def main():
    idem = f"smoke-{uuid4()}"
    headers = {"X-API-Key": KEY, "Idempotency-Key": idem}
    payment = {
        "amount": "149.90",
        "currency": "RUB",
        "description": "e2e smoke test",
        "metadata": {"run": idem},
        "webhook_url": "http://webhook-sink:9001/webhook",
    }
    status, first = request("POST", f"{API}/api/v1/payments", headers=headers, data=payment)
    assert status == 202, (status, first)
    status, duplicate = request("POST", f"{API}/api/v1/payments", headers=headers, data=payment)
    assert status == 202 and first["payment_id"] == duplicate["payment_id"]
    status, conflict = request(
        "POST", f"{API}/api/v1/payments", headers=headers,
        data={**payment, "description": "a different payment"},
    )
    assert status == 409, (status, conflict)
    payment_id = first["payment_id"]
    print("Created payment:", payment_id)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        status, detail = request(
            "GET", f"{API}/api/v1/payments/{payment_id}", headers={"X-API-Key": KEY}
        )
        assert status == 200, (status, detail)
        if detail["status"] != "pending" and detail["webhook_delivered_at"]:
            assert detail["status"] in ("succeeded", "failed")
            assert detail["webhook_attempts"] >= 1
            _, events = request("GET", f"{SINK}/events")
            assert any(e["payment_id"] == payment_id for e in events)
            print("PASS: idempotency, conflict, processing, signed webhook delivery")
            print(json.dumps(detail, ensure_ascii=False, indent=2))
            return
        time.sleep(0.5)
    raise TimeoutError("payment / webhook did not finish before smoke deadline")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        raise
