import { PageHeader } from "@/components/ui/page-header";
import { requireApiClient } from "@/lib/api-server";

import { TablesExplorer } from "./tables-explorer";

export default async function TablesPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;
  const client = await requireApiClient();

  let tables: Awaited<ReturnType<typeof client.listTables>> = [];
  try {
    tables = await client.listTables(orgId, projectId, databaseId);
  } catch {
    // Database not running — tables genuinely unavailable, not an error to surface loudly.
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Tables" description="Browse the rows in this database's tables." />
      <TablesExplorer organizationId={orgId} projectId={projectId} databaseId={databaseId} tables={tables} />
    </div>
  );
}
