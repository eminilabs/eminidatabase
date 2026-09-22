import { PageHeader } from "@/components/ui/page-header";

import { ExtensionsCard } from "../extensions-card";

export default async function ExtensionsPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;

  return (
    <div className="space-y-6">
      <PageHeader title="Extensions" description="Postgres extensions installed on this database." />
      <ExtensionsCard organizationId={orgId} projectId={projectId} databaseId={databaseId} />
    </div>
  );
}
