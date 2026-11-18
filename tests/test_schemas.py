from decimal import Decimal

import pytest
from pydantic import ValidationError

from payment_service.schemas import PaymentCreate, PaymentEvent


@pytest.fixture
def payload():
    return {
        "amount": "123.40",
        "currency": "RUB",
        "description": "Order 42",
        "metadata": {"order": 42},
        "webhook_url": "https://client.example/webhook",
    }


def test_amount_remains_decimal(payload):
    payment = PaymentCreate.model_validate(payload)
    assert payment.amount == Decimal("123.40")
    assert payment.model_dump(mode="json")["amount"] == "123.40"


def test_semantically_identical_amounts_share_fingerprint(payload):
    one = PaymentCreate.model_validate(payload)
    other = PaymentCreate.model_validate({**payload, "amount": "123.4"})
    assert one.fingerprint() == other.fingerprint()


def test_json_key_order_does_not_change_fingerprint(payload):
    one = PaymentCreate.model_validate({**payload, "metadata": {"a": 1, "b": 2}})
    two = PaymentCreate.model_validate({**payload, "metadata": {"b": 2, "a": 1}})
    assert one.fingerprint() == two.fingerprint()


@pytest.mark.parametrize("amount", ["0", "-1", "0.001", "NaN", "Infinity", "10000000000000000"])
def test_reject_invalid_amount(payload, amount):
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate({**payload, "amount": amount})


def test_reject_currency_outside_allowlist(payload):
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate({**payload, "currency": "GBP"})


def test_reject_metadata_with_nan(payload):
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate({**payload, "metadata": {"bad": float("nan")}})


def test_reject_oversize_metadata(payload):
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate({**payload, "metadata": {"x": "z" * 20_000}})


def test_reject_unknown_payload_field(payload):
    with pytest.raises(ValidationError):
        PaymentCreate.model_validate({**payload, "secret": "unexpected"})


def test_attempt_is_bounded():
    from uuid import uuid4

    with pytest.raises(ValidationError):
        PaymentEvent(event_id=uuid4(), payment_id=uuid4(), attempt=4)
