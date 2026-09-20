"""Payment provider abstraction (docs/architecture/08 §8.10, cahier des charges
§47) — decouples savings/loan cash movement from any specific payment rail, so
a real mobile money integration (Orange Money, MTN MoMo, ...) plugs in here
without touching mf_app/services/savings.py or loans.py.

No real provider is wired up in this phase — that needs real sandbox
credentials from a specific mobile money operator, which this project has
none of. Same "abstraction built, real integration deferred" pattern already
used elsewhere in this codebase (TypeScript SDKs deferred Phase 8→F, PITR
deferred Phase 5→6): the interface is real and tested, the integration is an
honest, documented gap, not a half-built stub pretending to work.

ManualPaymentProvider is what Phases 9.1-9.3 actually use: physical cash
handled by a teller, modeled as always-immediate since there's no external
system to await. A real mobile money provider would implement the same
interface and, from its webhook handler, call the exact same
deposit()/withdraw()/repay_installment() functions — just with the money's
origin being a phone number instead of a teller's till.
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
    async def collect(
        self, *, phone_or_account: str, amount: Decimal, reference: str
    ) -> PaymentResult:
        """Pull money FROM the customer (a savings deposit, a loan repayment)."""

    @abstractmethod
    async def disburse(
        self, *, phone_or_account: str, amount: Decimal, reference: str
    ) -> PaymentResult:
        """Push money TO the customer (a savings withdrawal, a loan disbursement)."""


class ManualPaymentProvider(PaymentProvider):
    async def collect(
        self, *, phone_or_account: str, amount: Decimal, reference: str
    ) -> PaymentResult:
        return PaymentResult(provider_reference=reference, status="completed")

    async def disburse(
        self, *, phone_or_account: str, amount: Decimal, reference: str
    ) -> PaymentResult:
        return PaymentResult(provider_reference=reference, status="completed")
