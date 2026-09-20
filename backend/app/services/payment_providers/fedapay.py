"""FedaPay client — mobile money payments (cahier des charges §47). Raw REST via
httpx, deliberately not a pip package: FedaPay publishes no official Python SDK
(only PHP/Node/Ruby), and the direct "collect" endpoints used below to charge a
mobile money number without any redirect aren't wrapped by those official SDKs
either — they're called here exactly as any of this codebase's other outbound
HTTP calls are (agent RPCs, webhook delivery, NOWPayments).

Flow (no hosted checkout page, no browser redirect):
  1. create_transaction()          POST /transactions
  2. generate_token()              POST /transactions/{id}/token
  3. charge_mobile_money()         POST /{mode}   (root-level, not /transactions/{mode})
     -> triggers a USSD/app prompt on the customer's own phone.
  4. The actual outcome (approved/declined) arrives only via webhook — step 3
     merely confirms the charge was *initiated*.
"""

from __future__ import annotations

import hashlib
import hmac
import time

import httpx

from app.core.config import get_settings

_SANDBOX_BASE = "https://sandbox-api.fedapay.com/v1"
_LIVE_BASE = "https://api.fedapay.com/v1"

# One "collect" endpoint per mobile money operator/country pair, as documented by
# FedaPay for direct (non-redirect) charges. The country here is authoritative —
# callers must never forward a client-supplied country instead, or a
# mode/country mismatch could route a charge incorrectly.
MOBILE_MONEY_OPERATORS: dict[str, dict[str, str]] = {
    "mtn_open": {"country": "bj", "label": "MTN Mobile Money (Bénin)"},
    "moov": {"country": "bj", "label": "Moov Money (Bénin)"},
    "sbin": {"country": "bj", "label": "Celtiis Cash (Bénin)"},
    "moov_tg": {"country": "tg", "label": "Moov Money (Togo)"},
    "togocel": {"country": "tg", "label": "Mixx By Yas (Togo)"},
    "mtn_ci": {"country": "ci", "label": "MTN Mobile Money (Côte d'Ivoire)"},
    "airtel_ne": {"country": "ne", "label": "Airtel Money (Niger)"},
    "free_sn": {"country": "sn", "label": "Free Money (Sénégal)"},
}

_WEBHOOK_TOLERANCE_SECONDS = 300


class FedaPayError(RuntimeError):
    pass


def _base_url() -> str:
    return _SANDBOX_BASE if get_settings().fedapay_environment == "sandbox" else _LIVE_BASE


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_settings().fedapay_secret_key}"}


async def create_transaction(
    *, amount: int, currency: str, description: str, customer_email: str
) -> str:
    """Returns the transaction id. `amount` is in the currency's major unit (e.g.
    whole XOF, not cents — XOF has no minor unit)."""
    async with httpx.AsyncClient(base_url=_base_url(), timeout=15) as client:
        resp = await client.post(
            "/transactions",
            headers=_headers(),
            json={
                "description": description,
                "amount": amount,
                "currency": {"iso": currency},
                "customer": {"email": customer_email},
            },
        )
    if resp.status_code >= 400:
        raise FedaPayError(
            f"FedaPay create_transaction failed: {resp.status_code} {resp.text[:500]}"
        )
    body = resp.json()
    transaction = body.get("v1/transaction", body)
    return str(transaction["id"])


async def get_transaction_status(transaction_id: str) -> dict:
    """Reconciliation path for when a webhook never arrives (not yet registered
    in FedaPay's dashboard, or lost) or a charge call's outcome was genuinely
    unknown locally (e.g. a client-side timeout on `charge_mobile_money` — proven
    live to not imply the charge itself failed on FedaPay's side)."""
    async with httpx.AsyncClient(base_url=_base_url(), timeout=15) as client:
        resp = await client.get(f"/transactions/{transaction_id}", headers=_headers())
    if resp.status_code >= 400:
        raise FedaPayError(
            f"FedaPay get_transaction_status failed: {resp.status_code} {resp.text[:500]}"
        )
    body = resp.json()
    return body.get("v1/transaction", body)


async def generate_token(transaction_id: str) -> str:
    async with httpx.AsyncClient(base_url=_base_url(), timeout=15) as client:
        resp = await client.post(f"/transactions/{transaction_id}/token", headers=_headers())
    if resp.status_code >= 400:
        raise FedaPayError(f"FedaPay generate_token failed: {resp.status_code} {resp.text[:500]}")
    return resp.json()["token"]


async def charge_mobile_money(*, token: str, mode: str, phone_number: str) -> None:
    """Initiates a direct mobile money charge — no redirect, no hosted checkout
    page. The customer approves via a USSD prompt / operator app on their own
    phone; the eventual approved/declined outcome only arrives via webhook."""
    operator = MOBILE_MONEY_OPERATORS.get(mode)
    if operator is None:
        raise FedaPayError(f"Unsupported mobile money mode: {mode!r}")
    async with httpx.AsyncClient(base_url=_base_url(), timeout=15) as client:
        resp = await client.post(
            f"/{mode}",
            headers=_headers(),
            json={
                "token": token,
                "phone_number": {"number": phone_number, "country": operator["country"]},
            },
        )
    if resp.status_code >= 400:
        raise FedaPayError(
            f"FedaPay charge_mobile_money failed: {resp.status_code} {resp.text[:500]}"
        )


def _sign(secret: str, timestamp: str, body: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()


def verify_webhook_signature(body: bytes, signature_header: str) -> bool:
    """Header format is Stripe-like: "t=<unix ts>,s=<hex hmac>[,s=<hex hmac>...]".
    Rejects both a bad signature and a replayed old one (timestamp drift beyond
    `_WEBHOOK_TOLERANCE_SECONDS`)."""
    parts: dict[str, list[str]] = {"t": [], "s": []}
    for chunk in signature_header.split(","):
        key, _, value = chunk.partition("=")
        key = key.strip()
        if key in parts:
            parts[key].append(value.strip())
    if not parts["t"] or not parts["s"]:
        return False

    timestamp = parts["t"][0]
    if abs(time.time() - int(timestamp)) > _WEBHOOK_TOLERANCE_SECONDS:
        return False

    expected = _sign(get_settings().fedapay_webhook_secret, timestamp, body.decode())
    return any(hmac.compare_digest(expected, s) for s in parts["s"])
