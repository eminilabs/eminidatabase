"use client";

import { useActionState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { payManuallyAction, payWithCryptoAction, payWithMobileMoneyAction } from "./actions";

// Mirrors backend/app/services/payment_providers/fedapay.py's
// MOBILE_MONEY_OPERATORS — the backend doesn't expose this list via an
// endpoint, so it's kept in sync here manually.
const MOBILE_MONEY_OPERATORS = [
  { mode: "mtn_open", label: "MTN Mobile Money (Bénin)" },
  { mode: "moov", label: "Moov Money (Bénin)" },
  { mode: "sbin", label: "Celtiis Cash (Bénin)" },
  { mode: "moov_tg", label: "Moov Money (Togo)" },
  { mode: "togocel", label: "Mixx By Yas (Togo)" },
  { mode: "mtn_ci", label: "MTN Mobile Money (Côte d'Ivoire)" },
  { mode: "airtel_ne", label: "Airtel Money (Niger)" },
  { mode: "free_sn", label: "Free Money (Sénégal)" },
];

export function PayForms({ organizationId, invoiceId }: { organizationId: string; invoiceId: string }) {
  const [manualPending, startManual] = useTransition();
  const cryptoAction = payWithCryptoAction.bind(null, organizationId, invoiceId);
  const [cryptoState, cryptoFormAction, cryptoPending] = useActionState(cryptoAction, undefined);
  const mobileMoneyAction = payWithMobileMoneyAction.bind(null, organizationId, invoiceId);
  const [mmState, mmFormAction, mmPending] = useActionState(mobileMoneyAction, undefined);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Manual (bank transfer / cash)</h3>
        <Button
          disabled={manualPending}
          onClick={() => startManual(() => payManuallyAction(organizationId, invoiceId))}
        >
          {manualPending ? "Confirming…" : "Confirm payment received"}
        </Button>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Crypto (NOWPayments)</h3>
        <form action={cryptoFormAction} className="flex items-end gap-2">
          {cryptoState?.error && (
            <div className="w-full">
              <Alert>{cryptoState.error}</Alert>
            </div>
          )}
          <div>
            <Label htmlFor="pay_currency">Currency</Label>
            <Input id="pay_currency" name="pay_currency" placeholder="usdtbsc" className="w-40" />
          </div>
          <Button type="submit" variant="outline" disabled={cryptoPending}>
            {cryptoPending ? "Creating…" : "Get deposit address"}
          </Button>
        </form>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Mobile money (FedaPay)</h3>
        <form action={mmFormAction} className="flex flex-wrap items-end gap-2">
          {mmState?.error && (
            <div className="w-full">
              <Alert>{mmState.error}</Alert>
            </div>
          )}
          <div>
            <Label htmlFor="mode">Operator</Label>
            <select
              id="mode"
              name="mode"
              required
              className="h-10 w-64 rounded-md border border-slate-300 bg-white px-3 text-sm"
            >
              {MOBILE_MONEY_OPERATORS.map((op) => (
                <option key={op.mode} value={op.mode}>
                  {op.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="phone_number">Phone number</Label>
            <Input id="phone_number" name="phone_number" required className="w-40" />
          </div>
          <Button type="submit" variant="outline" disabled={mmPending}>
            {mmPending ? "Charging…" : "Charge mobile money"}
          </Button>
        </form>
      </div>
    </div>
  );
}
