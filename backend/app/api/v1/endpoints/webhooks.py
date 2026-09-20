from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_membership
from app.core.security import generate_random_password
from app.db.session import get_db
from app.models.membership import Membership
from app.models.user import User
from app.models.webhook import Webhook
from app.models.webhook_delivery import WebhookDelivery
from app.schemas.webhook import (
    WebhookCreate,
    WebhookCreated,
    WebhookDeliveryResponse,
    WebhookResponse,
)
from app.services.audit import record_audit
from app.services.rbac import require_permission
from app.services.secrets import encrypt_secret

router = APIRouter(prefix="/organizations/{organization_id}/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookCreated, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    organization_id: uuid.UUID,
    payload: WebhookCreate,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WebhookCreated:
    require_permission(membership.role, "webhooks:manage")

    secret = generate_random_password(32)
    webhook = Webhook(
        organization_id=organization_id,
        url=payload.url,
        encrypted_secret=encrypt_secret(secret),
        event_types=payload.event_types,
    )
    db.add(webhook)
    await db.flush()

    await record_audit(
        db,
        action="WEBHOOK_CREATED",
        resource_type="webhook",
        resource_id=webhook.id,
        organization_id=organization_id,
        user_id=current_user.id,
        after={"url": webhook.url, "event_types": payload.event_types},
    )
    await db.commit()

    return WebhookCreated(
        id=webhook.id, url=webhook.url, event_types=payload.event_types, secret=secret
    )


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
    organization_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[Webhook]:
    require_permission(membership.role, "webhooks:manage")
    result = await db.execute(select(Webhook).where(Webhook.organization_id == organization_id))
    return list(result.scalars().all())


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_webhook(
    organization_id: uuid.UUID,
    webhook_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    require_permission(membership.role, "webhooks:manage")
    webhook = await db.get(Webhook, webhook_id)
    if webhook is None or str(webhook.organization_id) != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    await db.delete(webhook)
    await record_audit(
        db,
        action="WEBHOOK_DELETED",
        resource_type="webhook",
        resource_id=webhook_id,
        organization_id=organization_id,
        user_id=current_user.id,
        before={"url": webhook.url},
    )
    await db.commit()


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_deliveries(
    organization_id: uuid.UUID,
    webhook_id: uuid.UUID,
    membership: Membership = Depends(get_membership),
    db: AsyncSession = Depends(get_db),
) -> list[WebhookDelivery]:
    require_permission(membership.role, "webhooks:manage")
    webhook = await db.get(Webhook, webhook_id)
    if webhook is None or str(webhook.organization_id) != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
    )
    return list(result.scalars().all())
