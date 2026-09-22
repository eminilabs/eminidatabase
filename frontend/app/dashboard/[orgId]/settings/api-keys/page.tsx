import { Key } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { requireApiClient } from "@/lib/api-server";

import { CreateApiKeyForm } from "./create-api-key-form";
import { RevokeApiKeyButton } from "./revoke-api-key-button";

export default async function ApiKeysPage({
  params,
}: {
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const client = await requireApiClient();
  const keys = await client.listApiKeys(orgId);

  return (
    <div className="space-y-6">
      <PageHeader title="API keys" description="Used to authenticate programmatic access to this organization." />

      <Card>
        <CardContent className="py-4">
          <CreateApiKeyForm organizationId={orgId} />
        </CardContent>
      </Card>

      {keys.length === 0 ? (
        <EmptyState icon={Key} title="No API keys yet" description="Create one above to authenticate API requests." />
      ) : (
        <Card>
          <ul className="divide-y divide-slate-800 text-sm">
            {keys.map((key) => (
              <li key={key.id} className="flex items-center justify-between px-6 py-3">
                <div className="flex items-center gap-3">
                  <Key className="h-4 w-4 text-slate-500" />
                  <div>
                    <p className="font-medium text-slate-100">{key.name}</p>
                    <p className="font-mono text-xs text-slate-500">{key.key_prefix}…</p>
                  </div>
                </div>
                <RevokeApiKeyButton organizationId={orgId} apiKeyId={key.id} />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
