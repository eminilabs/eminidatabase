import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { requireApiClient } from "@/lib/api-server";

import { BackupPolicyForm } from "./backup-policy-form";
import { BackupRow } from "./backup-row";
import { CreateBackupButton } from "./create-backup-button";

export default async function BackupsPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;
  const client = await requireApiClient();
  const [backups, policy] = await Promise.all([
    client.listBackups(orgId, projectId, databaseId),
    client.getBackupPolicy(orgId, projectId, databaseId),
  ]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Backup policy</CardTitle>
        </CardHeader>
        <CardContent>
          <BackupPolicyForm
            organizationId={orgId}
            projectId={projectId}
            databaseId={databaseId}
            policy={policy}
          />
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-300">Backups</h2>
        <CreateBackupButton organizationId={orgId} projectId={projectId} databaseId={databaseId} />
      </div>

      {backups.length === 0 ? (
        <p className="text-sm text-slate-500">No backups yet.</p>
      ) : (
        <div className="space-y-3">
          {backups.map((backup) => (
            <BackupRow
              key={backup.id}
              organizationId={orgId}
              projectId={projectId}
              databaseId={databaseId}
              initialBackup={backup}
            />
          ))}
        </div>
      )}
    </div>
  );
}
