"""Payment provider abstraction (cahier des charges §47, cf. docs/architecture/
08 §8.12/§8.15) — decouples invoice settlement from any specific payment
gateway (Stripe, a bank transfer confirmation, ...). Deliberately duplicated
rather than imported from microfinance/mf_app/services/payments.py: these are
two separate deployables with no shared dependency, exactly like the GUID
column type or identifier validation are already duplicated between backend/
and agent/ (cf. that module's docstring for the same reasoning).

No real gateway is wired up — that needs real merchant/sandbox credentials
this project has none of. ManualPaymentProvider models what actually exists
today: an owner manually confirming a bank transfer or cash payment landed,
via POST .../invoices/{id}/pay, marks it PAID immediately. A real Stripe (or
similar) integration would implement this same interface from its webhook
handler instead.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaymentResult:
    provider_reference: str
    status: str  # "completed" | "pending" | "failed"


class PaymentProvider(ABC):
    @abstractmethod
    async def charge(
        self, *, organization_reference: str, amount: Decimal, currency: str, reference: str
    ) -> PaymentResult:
        """Attempt to collect `amount` for an invoice."""


class ManualPaymentProvider(PaymentProvider):
    async def charge(
        self, *, organization_reference: str, amount: Decimal, currency: str, reference: str
    ) -> PaymentResult:
        return PaymentResult(provider_reference=reference, status="completed")
