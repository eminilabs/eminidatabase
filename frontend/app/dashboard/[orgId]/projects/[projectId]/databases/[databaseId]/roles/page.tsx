import { PageHeader } from "@/components/ui/page-header";

import { RolesCard } from "../roles-card";

export default async function RolesPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;

  return (
    <div className="space-y-6">
      <PageHeader title="Roles" description="Database credentials used to connect to this database." />
      <RolesCard organizationId={orgId} projectId={projectId} databaseId={databaseId} />
    </div>
  );
}
