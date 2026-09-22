import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { requireApiClient } from "@/lib/api-server";

export default async function WebhookDeliveriesPage({
  params,
}: {
  params: Promise<{ orgId: string; webhookId: string }>;
}) {
  const { orgId, webhookId } = await params;
  const client = await requireApiClient();
  const deliveries = await client.listWebhookDeliveries(orgId, webhookId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Deliveries</CardTitle>
      </CardHeader>
      <CardContent>
        {deliveries.length === 0 ? (
          <p className="text-sm text-slate-500">No deliveries yet.</p>
        ) : (
          <ul className="divide-y divide-slate-800 text-sm">
            {deliveries.map((delivery) => (
              <li key={delivery.id} className="flex items-center justify-between py-2">
                <span className="text-slate-500">{delivery.event_type}</span>
                <span
                  className={delivery.status === "succeeded" ? "text-green-600" : "text-red-600"}
                >
                  {delivery.status}
                  {delivery.response_code ? ` (${delivery.response_code})` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
