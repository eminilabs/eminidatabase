"""Webhook delivery — cf. docs/architecture/07-api-cli-sdk.md §7.4.

Deliveries are jobs in the same `jobs` table as everything else in this platform
(app/services/jobs.py) rather than a bespoke delivery queue: the existing
retry/backoff machinery is exactly "retries avec backoff" (§7.4) for free, and it
keeps "how does this platform run something asynchronously" down to one answer.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utcnow
from app.models.job import Job
from app.models.webhook import Webhook
from app.models.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from app.services.jobs import enqueue
from app.services.secrets import decrypt_secret

DELIVERY_TIMEOUT_SECONDS = 10.0


async def emit_event(
    db: AsyncSession, organization_id: uuid.UUID | None, event_type: str, data: dict
) -> None:
    """Called from job handlers at the moment something webhook-worthy happens
    (cf. app/services/orchestrator.py, app/services/backup_orchestrator.py,
    app/worker.py's terminal-failure paths). A no-op if there's no organization to
    scope subscriptions to, or no active subscriber for this event type."""
    if organization_id is None:
        return

    webhooks = (
        (
            await db.execute(
                select(Webhook).where(
                    Webhook.organization_id == organization_id, Webhook.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    for webhook in webhooks:
        if event_type not in webhook.event_types:
            continue
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event_type=event_type,
            payload={"event": event_type, "data": data},
        )
        db.add(delivery)
        await db.flush()
        await enqueue(
            db,
            type="deliver_webhook",
            payload={"delivery_id": str(delivery.id)},
            resource_type="webhook_delivery",
            resource_id=delivery.id,
        )


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def execute_deliver_webhook(db: AsyncSession, job: Job) -> dict:
    delivery = await db.get(WebhookDelivery, uuid.UUID(job.payload["delivery_id"]))
    if delivery is None:
        raise RuntimeError(f"WebhookDelivery {job.payload['delivery_id']} not found")
    if delivery.status == WebhookDeliveryStatus.SUCCEEDED:
        return {"already_delivered": True}

    webhook = await db.get(Webhook, delivery.webhook_id)
    if webhook is None or not webhook.is_active:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.error = "Webhook was deleted or deactivated before delivery"
        return {"skipped": True}

    body = json.dumps(delivery.payload, sort_keys=True, default=str).encode()
    secret = decrypt_secret(webhook.encrypted_secret)
    signature = sign_payload(secret, body)

    async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            webhook.url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Eminidatabase-Event": delivery.event_type,
                "X-Eminidatabase-Signature": f"sha256={signature}",
            },
        )

    delivery.response_code = resp.status_code
    if resp.is_success:
        delivery.status = WebhookDeliveryStatus.SUCCEEDED
        delivery.delivered_at = utcnow()
        delivery.error = None
        return {"status_code": resp.status_code}

    raise RuntimeError(f"Webhook endpoint responded {resp.status_code}: {resp.text[:500]}")


WEBHOOK_HANDLERS = {
    "deliver_webhook": execute_deliver_webhook,
}
