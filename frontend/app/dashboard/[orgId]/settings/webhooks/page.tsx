import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { CreateWebhookForm } from "./create-webhook-form";
import { DeleteWebhookButton } from "./delete-webhook-button";

export default async function WebhooksPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await getApiClient();
  const webhooks = await client.listWebhooks(orgId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Webhooks</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <CreateWebhookForm organizationId={orgId} />
        {webhooks.length === 0 ? (
          <p className="text-sm text-slate-400">No webhooks yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {webhooks.map((webhook) => (
              <li key={webhook.id} className="flex items-center justify-between py-2">
                <div>
                  <p className="font-medium text-slate-900">{webhook.url}</p>
                  <p className="text-xs text-slate-400">{webhook.event_types.join(", ")}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Link
                    href={`/dashboard/${orgId}/settings/webhooks/${webhook.id}/deliveries`}
                    className="text-slate-600 hover:underline"
                  >
                    Deliveries
                  </Link>
                  <DeleteWebhookButton organizationId={orgId} webhookId={webhook.id} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
