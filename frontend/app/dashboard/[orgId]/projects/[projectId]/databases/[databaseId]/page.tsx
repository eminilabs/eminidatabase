import { ConnectionCard } from "./connection-card";
import { ExtensionsCard } from "./extensions-card";
import { MetricsCard } from "./metrics-card";
import { RolesCard } from "./roles-card";

export default async function DatabaseOverviewPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <MetricsCard organizationId={orgId} projectId={projectId} databaseId={databaseId} />
      <ConnectionCard organizationId={orgId} projectId={projectId} databaseId={databaseId} />
      <ExtensionsCard organizationId={orgId} projectId={projectId} databaseId={databaseId} />
      <RolesCard organizationId={orgId} projectId={projectId} databaseId={databaseId} />
    </div>
  );
}
