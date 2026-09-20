import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getApiClient } from "@/lib/api-server";

import { MfaSetup } from "./mfa-setup";

export default async function SecuritySettingsPage() {
  const client = await getApiClient();
  const me = await client.me();

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <h1 className="text-xl font-semibold text-slate-900">Security</h1>

      <Card>
        <CardHeader>
          <CardTitle>Two-factor authentication</CardTitle>
        </CardHeader>
        <CardContent>
          {me.mfa_enabled ? (
            <p className="text-sm text-slate-600">
              Two-factor authentication is enabled on your account.
            </p>
          ) : (
            <MfaSetup />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
