import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { CreateApiKeyForm } from "./create-api-key-form";
import { RevokeApiKeyButton } from "./revoke-api-key-button";

export default async function ApiKeysPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await getApiClient();
  const keys = await client.listApiKeys(orgId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>API keys</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <CreateApiKeyForm organizationId={orgId} />
        {keys.length === 0 ? (
          <p className="text-sm text-slate-400">No API keys yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {keys.map((key) => (
              <li key={key.id} className="flex items-center justify-between py-2">
                <div>
                  <p className="font-medium text-slate-900">{key.name}</p>
                  <p className="font-mono text-xs text-slate-400">{key.key_prefix}…</p>
                </div>
                <RevokeApiKeyButton organizationId={orgId} apiKeyId={key.id} />
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
