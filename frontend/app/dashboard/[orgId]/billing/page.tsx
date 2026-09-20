import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { ChangePlanForm } from "./change-plan-form";

const STATUS_STYLES: Record<string, string> = {
  paid: "bg-green-100 text-green-800",
  finalized: "bg-amber-100 text-amber-800",
  draft: "bg-slate-100 text-slate-600",
  void: "bg-slate-100 text-slate-400",
};

export default async function BillingPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await getApiClient();
  const [subscription, plans, usage, invoices] = await Promise.all([
    client.getSubscription(orgId),
    client.listPlans(),
    client.getUsage(orgId),
    client.listInvoices(orgId),
  ]);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-slate-900">Billing</h1>

      <Card>
        <CardHeader>
          <CardTitle>Plan</CardTitle>
        </CardHeader>
        <CardContent>
          <ChangePlanForm organizationId={orgId} plans={plans} currentPlanId={subscription.plan_id} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Usage this period</CardTitle>
        </CardHeader>
        <CardContent>
          {usage.lines.length === 0 ? (
            <p className="text-sm text-slate-400">No usage recorded yet this period.</p>
          ) : (
            <ul className="divide-y divide-slate-100 text-sm">
              {usage.lines.map((line) => (
                <li key={line.metric} className="flex items-center justify-between py-2">
                  <span className="text-slate-600">{line.metric}</span>
                  <span className="font-medium text-slate-900">{line.total}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Invoices</CardTitle>
        </CardHeader>
        <CardContent>
          {invoices.length === 0 ? (
            <p className="text-sm text-slate-400">No invoices yet.</p>
          ) : (
            <ul className="divide-y divide-slate-100 text-sm">
              {invoices.map((invoice) => (
                <li key={invoice.id} className="flex items-center justify-between py-2">
                  <Link
                    href={`/dashboard/${orgId}/billing/invoices/${invoice.id}`}
                    className="text-slate-700 hover:underline"
                  >
                    {new Date(invoice.period_start).toLocaleDateString()} –{" "}
                    {new Date(invoice.period_end).toLocaleDateString()}
                  </Link>
                  <div className="flex items-center gap-3">
                    <span>
                      {invoice.total_amount} {invoice.currency}
                    </span>
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                        STATUS_STYLES[invoice.status] ?? "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {invoice.status}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
