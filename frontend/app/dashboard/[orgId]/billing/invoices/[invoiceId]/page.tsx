import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { InvoiceStatus } from "./invoice-status";

export default async function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ orgId: string; invoiceId: string }>;
}) {
  const { orgId, invoiceId } = await params;
  const client = await getApiClient();
  const [invoice, payments] = await Promise.all([
    client.getInvoice(orgId, invoiceId),
    client.listInvoicePayments(orgId, invoiceId),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">
          Invoice {new Date(invoice.period_start).toLocaleDateString()} –{" "}
          {new Date(invoice.period_end).toLocaleDateString()}
        </h1>
        <p className="text-sm text-slate-500">
          {invoice.total_amount} {invoice.currency}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Line items</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="divide-y divide-slate-100 text-sm">
            {invoice.line_items.map((item, i) => (
              <li key={i} className="flex items-center justify-between py-2">
                <span className="text-slate-600">{item.description}</span>
                <span className="font-medium text-slate-900">{item.amount}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Payment</CardTitle>
        </CardHeader>
        <CardContent>
          <InvoiceStatus organizationId={orgId} invoiceId={invoiceId} initialInvoice={invoice} />
        </CardContent>
      </Card>

      {payments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Payment attempts</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-slate-100 text-sm">
              {payments.map((payment) => (
                <li key={payment.id} className="flex items-center justify-between py-2">
                  <span className="text-slate-600">{payment.provider}</span>
                  <span>{payment.status}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
