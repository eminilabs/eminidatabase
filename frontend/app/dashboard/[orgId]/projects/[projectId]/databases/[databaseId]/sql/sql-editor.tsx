"use client";

import { sql } from "@codemirror/lang-sql";
import CodeMirror from "@uiw/react-codemirror";
import { githubDark } from "@uiw/codemirror-theme-github";
import { Database as DatabaseIcon, Play, Save, Table2, Trash2 } from "lucide-react";
import { useActionState, useState } from "react";

import type {
  QueryExecutionResponse,
  RoleResponse,
  SavedQueryResponse,
  SqlExecuteResponse,
  TableInfo,
} from "@eminidatabase/sdk";
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
  history,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  tables: TableInfo[];
  savedQueries: SavedQueryResponse[];
  roles: RoleResponse[];
  history: QueryExecutionResponse[];
}) {
  const [query, setQuery] = useState("");
  const [roleId, setRoleId] = useState("");
  const [result, setResult] = useState<SqlExecuteResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [localHistory, setLocalHistory] = useState(history);

  async function run() {
    if (!query.trim()) return;
    setRunning(true);
    setResult(null);
    const ranQuery = query;
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
      const succeeded = res.ok && !body.error;
      setLocalHistory((prev) => [
        {
          id: crypto.randomUUID(),
          query_text: ranQuery,
          status: succeeded ? "succeeded" : "failed",
        } as QueryExecutionResponse,
        ...prev,
      ]);
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
      <div className="space-y-5 lg:col-span-1">
        <div>
          <h3 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-600">Tables</h3>
          {tables.length === 0 ? (
            <p className="px-1 text-sm text-slate-500">No tables yet.</p>
          ) : (
            <ul className="space-y-0.5">
              {tables.map((table) => (
                <li key={table.name}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-slate-400 hover:bg-slate-800/60 hover:text-slate-100"
                    onClick={() => setQuery(`SELECT * FROM "${table.name}" LIMIT 100;`)}
                  >
                    <Table2 className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                    <span className="truncate">{table.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
            Saved queries
          </h3>
          {savedQueries.length === 0 ? (
            <p className="px-1 text-sm text-slate-500">None yet.</p>
          ) : (
            <ul className="space-y-0.5">
              {savedQueries.map((saved) => (
                <li key={saved.id} className="group flex items-center gap-1 rounded-md hover:bg-slate-800/60">
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate px-2 py-1.5 text-left text-sm text-slate-400 group-hover:text-slate-100"
                    onClick={() => setQuery(saved.query_text)}
                  >
                    {saved.name}
                  </button>
                  <button
                    type="button"
                    className="shrink-0 px-1.5 text-slate-600 hover:text-red-400"
                    onClick={() => deleteSavedQueryAction(organizationId, projectId, databaseId, saved.id)}
                    aria-label={`Delete saved query ${saved.name}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="space-y-3 lg:col-span-3">
        <div className="overflow-hidden rounded-md border border-slate-700">
          <CodeMirror
            value={query}
            onChange={setQuery}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
            }}
            height="220px"
            theme={githubDark}
            extensions={[sql()]}
            placeholder="SELECT * FROM ..."
            basicSetup={{ foldGutter: false }}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {roles.length > 0 && (
            <select
              value={roleId}
              onChange={(e) => setRoleId(e.target.value)}
              className="h-10 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm text-slate-200"
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
            <Play className="mr-1.5 h-4 w-4" />
            {running ? "Running…" : "Run (Ctrl+Enter)"}
          </Button>
          <Button variant="outline" onClick={() => setShowSaveForm((v) => !v)}>
            <Save className="mr-1.5 h-4 w-4" />
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
              <div className="overflow-x-auto rounded-md border border-slate-800">
                <table className="min-w-full divide-y divide-slate-800 text-sm">
                  <thead className="bg-slate-950/60">
                    <tr>
                      {result.columns.map((col) => (
                        <th
                          key={col}
                          className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {result.rows.map((row, i) => (
                      // Rows/cells have no stable id — the result set is a plain grid.
                      <tr key={i} className="hover:bg-slate-800/40">
                        {row.map((cell, j) => (
                          <td key={j} className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-300">
                            {cell === null ? <span className="text-slate-600">null</span> : String(cell)}
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

        {!result && (
          <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-slate-800 py-12 text-center text-slate-600">
            <DatabaseIcon className="h-6 w-6" />
            <p className="text-sm">Run a query to see results here.</p>
          </div>
        )}

        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-300">Recent queries</h3>
          {localHistory.length === 0 ? (
            <p className="text-sm text-slate-500">No queries run yet.</p>
          ) : (
            <ul className="divide-y divide-slate-800 text-sm">
              {localHistory.map((h) => (
                <li key={h.id}>
                  <button
                    type="button"
                    onClick={() => setQuery(h.query_text)}
                    className="flex w-full items-center justify-between gap-4 py-2 text-left hover:bg-slate-800/40"
                    title="Click to load this query into the editor"
                  >
                    <span className="truncate font-mono text-xs text-slate-500">{h.query_text}</span>
                    <span
                      className={h.status === "succeeded" ? "shrink-0 text-emerald-400" : "shrink-0 text-red-400"}
                    >
                      {h.status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
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
