import Link from "next/link";

import { StatusBadge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { requireApiClient } from "@/lib/api-server";

import { PricingCards } from "./pricing-cards";

export default async function BillingPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await requireApiClient();
  const [subscription, plans, usage, invoices] = await Promise.all([
    client.getSubscription(orgId),
    client.listPlans(),
    client.getUsage(orgId),
    client.listInvoices(orgId),
  ]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing"
        action={
          <a href="#invoices" className="text-sm text-slate-400 hover:text-slate-100 hover:underline">
            View/Pay invoices
          </a>
        }
      />

      <PricingCards organizationId={orgId} plans={plans} currentPlanId={subscription.plan_id} />

      <Card>
        <CardHeader>
          <CardTitle>Usage this period</CardTitle>
        </CardHeader>
        <CardContent>
          {usage.lines.length === 0 ? (
            <p className="text-sm text-slate-500">No usage recorded yet this period.</p>
          ) : (
            <ul className="divide-y divide-slate-800 text-sm">
              {usage.lines.map((line) => (
                <li key={line.metric} className="flex items-center justify-between py-2">
                  <span className="text-slate-500">{line.metric}</span>
                  <span className="font-medium text-slate-100">{line.total}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card id="invoices">
        <CardHeader>
          <CardTitle>Invoices</CardTitle>
        </CardHeader>
        <CardContent>
          {invoices.length === 0 ? (
            <p className="text-sm text-slate-500">No invoices yet.</p>
          ) : (
            <ul className="divide-y divide-slate-800 text-sm">
              {invoices.map((invoice) => (
                <li key={invoice.id} className="flex items-center justify-between py-2">
                  <Link
                    href={`/dashboard/${orgId}/billing/invoices/${invoice.id}`}
                    className="text-slate-300 hover:underline"
                  >
                    {new Date(invoice.period_start).toLocaleDateString()} –{" "}
                    {new Date(invoice.period_end).toLocaleDateString()}
                  </Link>
                  <div className="flex items-center gap-3">
                    <span>
                      {invoice.total_amount} {invoice.currency}
                    </span>
                    <StatusBadge status={invoice.status} />
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
