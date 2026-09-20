"""Inbound webhook endpoints for NOWPayments and FedaPay — cf.
app/services/payment_service.py for signature verification and settlement.
Deliberately unauthenticated (no bearer token, no membership dependency): these
are called by the gateways themselves, authenticated instead by their own HMAC
signature header — the same trust model this platform's own OUTBOUND webhook
deliveries use on the receiving end (app/services/webhook_orchestrator.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.payment_service import (
    PaymentWebhookError,
    handle_fedapay_webhook,
    handle_nowpayments_webhook,
)

router = APIRouter(prefix="/billing/webhooks", tags=["billing"])


@router.post("/nowpayments", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def nowpayments_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    signature = request.headers.get("x-nowpayments-sig")
    if not signature:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Missing x-nowpayments-sig header")
    body = await request.body()
    try:
        await handle_nowpayments_webhook(db, body, signature)
    except PaymentWebhookError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()


@router.post("/fedapay", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def fedapay_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    signature = request.headers.get("x-fedapay-signature")
    if not signature:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Missing x-fedapay-signature header"
        )
    body = await request.body()
    try:
        await handle_fedapay_webhook(db, body, signature)
    except PaymentWebhookError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
