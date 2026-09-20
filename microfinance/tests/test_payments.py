"""Unit test for the payment abstraction (docs/architecture/08 §8.10) — no DB,
no institution, just the interface's reference implementation."""

from decimal import Decimal

from mf_app.services.payments import ManualPaymentProvider


async def test_manual_provider_collect_completes_immediately():
    provider = ManualPaymentProvider()
    result = await provider.collect(
        phone_or_account="teller-desk", amount=Decimal("50.00"), reference="ref-1"
    )
    assert result.status == "completed"
    assert result.provider_reference == "ref-1"


async def test_manual_provider_disburse_completes_immediately():
    provider = ManualPaymentProvider()
    result = await provider.disburse(
        phone_or_account="teller-desk", amount=Decimal("50.00"), reference="ref-2"
    )
    assert result.status == "completed"
    assert result.provider_reference == "ref-2"
