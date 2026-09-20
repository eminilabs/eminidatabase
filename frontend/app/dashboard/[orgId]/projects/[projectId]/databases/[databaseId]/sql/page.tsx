import { getApiClient } from "@/lib/api-server";

import { SqlEditor } from "./sql-editor";

export default async function SqlEditorPage({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;
  const client = await getApiClient();

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
    <div className="space-y-8">
      <SqlEditor
        organizationId={orgId}
        projectId={projectId}
        databaseId={databaseId}
        tables={tables}
        savedQueries={savedQueries}
        roles={roles}
      />

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Recent queries</h3>
        {history.length === 0 ? (
          <p className="text-sm text-slate-400">No queries run yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {history.map((h) => (
              <li key={h.id} className="flex items-center justify-between gap-4 py-2">
                <span className="truncate font-mono text-xs text-slate-600">{h.query_text}</span>
                <span className={h.status === "succeeded" ? "text-green-600" : "text-red-600"}>
                  {h.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
