"use client";

import { useQuery } from "@tanstack/react-query";

import type { InvoiceDetailResponse } from "@eminidatabase/sdk";
import { Alert } from "@/components/ui/alert";

import { PayForms } from "./pay-forms";

const TERMINAL_STATUSES = new Set(["paid", "void"]);

export function InvoiceStatus({
  organizationId,
  invoiceId,
  initialInvoice,
}: {
  organizationId: string;
  invoiceId: string;
  initialInvoice: InvoiceDetailResponse;
}) {
  const { data: invoice } = useQuery({
    queryKey: ["invoice", invoiceId],
    queryFn: async (): Promise<InvoiceDetailResponse> => {
      const res = await fetch(`/api/organizations/${organizationId}/invoices/${invoiceId}`);
      if (!res.ok) throw new Error("Failed to load invoice status");
      return res.json();
    },
    initialData: initialInvoice,
    refetchInterval: (query) => (TERMINAL_STATUSES.has(query.state.data?.status ?? "") ? false : 3000),
  });

  const status = invoice?.status ?? initialInvoice.status;

  if (status === "paid") {
    return <Alert className="border-green-200 bg-green-50 text-green-800">Paid.</Alert>;
  }

  if (status !== "finalized") {
    return <p className="text-sm text-slate-500">This invoice is {status}.</p>;
  }

  return <PayForms organizationId={organizationId} invoiceId={invoiceId} />;
}
