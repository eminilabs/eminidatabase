"use client";

import { useActionState, useState } from "react";

import type { RoleResponse, SavedQueryResponse, SqlExecuteResponse, TableInfo } from "@eminidatabase/sdk";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { deleteSavedQueryAction, saveQueryAction } from "./actions";

export function SqlEditor({
  organizationId,
  projectId,
  databaseId,
  tables,
  savedQueries,
  roles,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  tables: TableInfo[];
  savedQueries: SavedQueryResponse[];
  roles: RoleResponse[];
}) {
  const [query, setQuery] = useState("");
  const [roleId, setRoleId] = useState("");
  const [result, setResult] = useState<SqlExecuteResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [showSaveForm, setShowSaveForm] = useState(false);

  async function run() {
    if (!query.trim()) return;
    setRunning(true);
    setResult(null);
    try {
      const res = await fetch(
        `/api/organizations/${organizationId}/projects/${projectId}/databases/${databaseId}/sql/execute`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, roleId: roleId || undefined }),
        }
      );
      const body = await res.json();
      if (!res.ok) {
        setResult({
          status: "failed",
          columns: [],
          rows: [],
          row_count: 0,
          truncated: false,
          duration_ms: 0,
          error: body.detail ?? "Query failed",
        });
        return;
      }
      setResult(body as SqlExecuteResponse);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
      <div className="space-y-4 lg:col-span-1">
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Tables</h3>
          <ul className="space-y-1 text-sm">
            {tables.map((table) => (
              <li key={table.name}>
                <button
                  type="button"
                  className="text-left text-slate-600 hover:text-slate-900 hover:underline"
                  onClick={() => setQuery(`SELECT * FROM "${table.name}" LIMIT 100;`)}
                >
                  {table.name}
                </button>
              </li>
            ))}
            {tables.length === 0 && <li className="text-slate-400">No tables yet.</li>}
          </ul>
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">Saved queries</h3>
          <ul className="space-y-1 text-sm">
            {savedQueries.map((saved) => (
              <li key={saved.id} className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  className="truncate text-left text-slate-600 hover:text-slate-900 hover:underline"
                  onClick={() => setQuery(saved.query_text)}
                >
                  {saved.name}
                </button>
                <button
                  type="button"
                  className="text-xs text-slate-400 hover:text-red-600"
                  onClick={() => deleteSavedQueryAction(organizationId, projectId, databaseId, saved.id)}
                >
                  delete
                </button>
              </li>
            ))}
            {savedQueries.length === 0 && <li className="text-slate-400">None yet.</li>}
          </ul>
        </div>
      </div>

      <div className="space-y-3 lg:col-span-3">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
          }}
          rows={8}
          placeholder="SELECT * FROM ..."
          className="w-full rounded-md border border-slate-300 bg-white p-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-slate-900/10"
        />
        <div className="flex flex-wrap items-center gap-3">
          {roles.length > 0 && (
            <select
              value={roleId}
              onChange={(e) => setRoleId(e.target.value)}
              className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm"
            >
              <option value="">Default role</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name ?? role.role_name}
                </option>
              ))}
            </select>
          )}
          <Button onClick={run} disabled={running || !query.trim()}>
            {running ? "Running…" : "Run (Ctrl+Enter)"}
          </Button>
          <Button variant="outline" onClick={() => setShowSaveForm((v) => !v)}>
            Save query
          </Button>
        </div>

        {showSaveForm && (
          <SaveQueryForm
            organizationId={organizationId}
            projectId={projectId}
            databaseId={databaseId}
            query={query}
          />
        )}

        {result && (
          <div className="space-y-2">
            {result.error ? (
              <Alert>{result.error}</Alert>
            ) : (
              <p className="text-xs text-slate-500">
                {result.row_count} row{result.row_count === 1 ? "" : "s"} · {result.duration_ms}ms
                {result.truncated ? " · truncated" : ""}
              </p>
            )}
            {result.columns.length > 0 && (
              <div className="overflow-x-auto rounded-md border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      {result.columns.map((col) => (
                        <th key={col} className="px-3 py-2 text-left font-medium text-slate-600">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {result.rows.map((row, i) => (
                      // Rows/cells have no stable id — the result set is a plain grid.
                      <tr key={i}>
                        {row.map((cell, j) => (
                          <td key={j} className="px-3 py-2 text-slate-700">
                            {cell === null ? <span className="text-slate-300">null</span> : String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SaveQueryForm({
  organizationId,
  projectId,
  databaseId,
  query,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  query: string;
}) {
  const boundAction = saveQueryAction.bind(null, organizationId, projectId, databaseId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  return (
    <form action={action} className="flex items-end gap-2">
      {state?.error && (
        <div className="w-full">
          <Alert>{state.error}</Alert>
        </div>
      )}
      <input type="hidden" name="query" value={query} />
      <Input name="name" placeholder="Query name" required className="w-56" />
      <Button type="submit" variant="outline" disabled={pending}>
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}
