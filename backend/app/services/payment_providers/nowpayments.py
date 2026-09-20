"""NOWPayments client — crypto payments (cahier des charges §47, closing the gap
documented in app/services/payments.py). Raw REST via httpx, no SDK: NOWPayments
doesn't publish an official Python client, and every other outbound HTTP call in
this codebase (agent RPCs, webhook delivery) already goes through httpx directly.

Uses the "Payment" API (a deposit address handed straight back), not "Invoice"
(which redirects to a NOWPayments-hosted page) — the crypto equivalent of FedaPay's
non-redirect requirement, even though only FedaPay's was spelled out explicitly.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from app.core.config import get_settings

_SANDBOX_BASE = "https://api-sandbox.nowpayments.io/v1"
_LIVE_BASE = "https://api.nowpayments.io/v1"


class NowPaymentsError(RuntimeError):
    pass


def _base_url() -> str:
    return _SANDBOX_BASE if get_settings().nowpayments_sandbox else _LIVE_BASE


def _headers() -> dict:
    return {"x-api-key": get_settings().nowpayments_api_key, "Content-Type": "application/json"}


async def create_payment(
    *,
    price_amount: float,
    price_currency: str,
    order_id: str,
    order_description: str,
    pay_currency: str,
) -> dict:
    """Creates a payment collecting `price_amount` of `price_currency` (the
    invoice's own fiat currency — never a crypto amount, which would drift with
    the exchange rate between request and settlement), denominated in
    `pay_currency` crypto."""
    settings = get_settings()
    callback_url = f"{settings.nowpayments_public_api_url}/api/v1/billing/webhooks/nowpayments"
    payload = {
        "price_amount": price_amount,
        "price_currency": price_currency,
        "pay_currency": pay_currency,
        "order_id": order_id,
        "order_description": order_description,
        "ipn_callback_url": callback_url,
        "is_fixed_rate": False,
        "is_fee_paid_by_user": False,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{_base_url()}/payment", headers=_headers(), json=payload)
    if resp.status_code >= 400:
        raise NowPaymentsError(
            f"NOWPayments create_payment failed: {resp.status_code} {resp.text[:500]}"
        )
    return resp.json()


async def get_payment_status(payment_id: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{_base_url()}/payment/{payment_id}", headers=_headers())
    if resp.status_code >= 400:
        raise NowPaymentsError(
            f"NOWPayments get_payment_status failed: {resp.status_code} {resp.text[:500]}"
        )
    return resp.json()


def verify_ipn_signature(payload_bytes: bytes, received_sig: str) -> bool:
    """HMAC-SHA512 over the JSON body re-serialized with sorted keys, compact
    separators, and `ensure_ascii=False` — NOWPayments signs the raw UTF-8 bytes of
    non-ASCII characters, while `json.dumps`'s default `ensure_ascii=True` would
    escape them to `\\uXXXX` first and produce a different signature entirely."""
    body = json.loads(payload_bytes)
    sorted_body = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(
        get_settings().nowpayments_ipn_secret.encode(), sorted_body.encode(), hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(expected, received_sig.lower())
