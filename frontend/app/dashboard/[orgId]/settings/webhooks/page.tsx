import { Webhook as WebhookIcon } from "lucide-react";
import Link from "next/link";

import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { requireApiClient } from "@/lib/api-server";

import { CreateWebhookForm } from "./create-webhook-form";
import { DeleteWebhookButton } from "./delete-webhook-button";

export default async function WebhooksPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await requireApiClient();
  const webhooks = await client.listWebhooks(orgId);

  return (
    <div className="space-y-6">
      <PageHeader title="Webhooks" description="Get notified when events happen in this organization." />

      <Card>
        <CardContent className="py-4">
          <CreateWebhookForm organizationId={orgId} />
        </CardContent>
      </Card>

      {webhooks.length === 0 ? (
        <EmptyState icon={WebhookIcon} title="No webhooks yet" description="Create one above to receive event notifications." />
      ) : (
        <Card>
          <ul className="divide-y divide-slate-800 text-sm">
            {webhooks.map((webhook) => (
              <li key={webhook.id} className="flex items-center justify-between px-6 py-3">
                <div className="flex items-center gap-3">
                  <WebhookIcon className="h-4 w-4 text-slate-500" />
                  <div>
                    <p className="font-medium text-slate-100">{webhook.url}</p>
                    <p className="text-xs text-slate-500">{webhook.event_types.join(", ")}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Link
                    href={`/dashboard/${orgId}/settings/webhooks/${webhook.id}/deliveries`}
                    className="text-slate-500 hover:underline"
                  >
                    Deliveries
                  </Link>
                  <DeleteWebhookButton organizationId={orgId} webhookId={webhook.id} />
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
