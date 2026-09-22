import { PageHeader } from "@/components/ui/page-header";
import { requireApiClient } from "@/lib/api-server";

import { SqlEditor } from "./sql-editor";

export default async function SqlEditorPage({
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
    // Database not running — schema browser genuinely empty, not an error to surface.
  }

  const [savedQueries, roles, history] = await Promise.all([
    client.listSavedQueries(orgId, projectId, databaseId),
    client.listRoles(orgId, projectId, databaseId),
    client.getSqlHistory(orgId, projectId, databaseId, 20),
  ]);

  return (
    <div className="space-y-6">
      <PageHeader title="SQL Editor" description="Run SQL directly against this database." />
      <SqlEditor
        organizationId={orgId}
        projectId={projectId}
        databaseId={databaseId}
        tables={tables}
        savedQueries={savedQueries}
        roles={roles}
        history={history}
      />
    </div>
  );
}
