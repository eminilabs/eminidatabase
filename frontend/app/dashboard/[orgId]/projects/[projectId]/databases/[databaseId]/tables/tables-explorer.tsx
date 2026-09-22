"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { SqlExecuteResponse, TableInfo } from "@eminidatabase/sdk";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Plus,
  RefreshCw,
  Search,
  Table2,
  Trash2,
} from "lucide-react";
import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

function escapeSqlString(value: string): string {
  return value.replace(/'/g, "''");
}

// The `_pkey` index Postgres creates automatically for every PRIMARY KEY is
// the only reliable way to identify a row for UPDATE/DELETE — the schema
// endpoint doesn't expose a separate `primary_key` flag, and inventing one
// server-side isn't in scope here, so it's parsed out of the index definition
// (`CREATE UNIQUE INDEX x_pkey ON public.x USING btree (col1, col2)`).
function primaryKeyColumns(table: TableInfo): string[] {
  const pk = table.indexes.find((idx) => idx.name.endsWith("_pkey"));
  if (!pk) return [];
  const match = pk.definition.match(/\(([^)]+)\)\s*$/);
  if (!match) return [];
  return match[1].split(",").map((c) => c.trim().replace(/^"+|"+$/g, ""));
}

function cellLiteral(value: unknown): string {
  return value === null ? "IS NULL" : `= '${escapeSqlString(String(value))}'`;
}

function buildRowWhere(pkColumns: string[], columns: string[], row: unknown[]): string {
  return pkColumns
    .map((pk) => {
      const idx = columns.indexOf(pk);
      const value = idx >= 0 ? row[idx] : null;
      return `"${pk}" ${cellLiteral(value)}`;
    })
    .join(" AND ");
}

async function runSql(
  organizationId: string,
  projectId: string,
  databaseId: string,
  query: string
): Promise<SqlExecuteResponse> {
  const res = await fetch(
    `/api/organizations/${organizationId}/projects/${projectId}/databases/${databaseId}/sql/execute`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    }
  );
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail ?? "Query failed");
  // A failed statement (e.g. a NOT NULL violation) comes back as 200 with
  // `error` set, matching the SQL Editor's own result shape — surface it the
  // same way here instead of treating it as a successful response.
  if (body.error) throw new Error(body.error);
  return body as SqlExecuteResponse;
}

export function TablesExplorer({
  organizationId,
  projectId,
  databaseId,
  tables,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  tables: TableInfo[];
}) {
  const [tableQuery, setTableQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(tables[0]?.name ?? null);
  const [page, setPage] = useState(0);
  const [dataSearch, setDataSearch] = useState("");
  const [sort, setSort] = useState<{ column: string; dir: "asc" | "desc" } | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());
  const [editingCell, setEditingCell] = useState<{ row: number; column: string } | null>(null);
  const [cellError, setCellError] = useState<string | null>(null);
  const [savingCell, setSavingCell] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const queryClient = useQueryClient();

  const selectedTable = tables.find((t) => t.name === selected) ?? null;
  const pkColumns = useMemo(() => (selectedTable ? primaryKeyColumns(selectedTable) : []), [selectedTable]);
  const editable = pkColumns.length > 0;

  const filteredTables = useMemo(() => {
    const q = tableQuery.trim().toLowerCase();
    if (!q) return tables;
    return tables.filter((t) => t.name.toLowerCase().includes(q));
  }, [tables, tableQuery]);

  const whereClause = useMemo(() => {
    if (!dataSearch.trim() || !selectedTable) return "";
    const escaped = escapeSqlString(dataSearch.trim());
    const conditions = selectedTable.columns.map((c) => `"${c.name}"::text ILIKE '%${escaped}%'`);
    return ` WHERE ${conditions.join(" OR ")}`;
  }, [dataSearch, selectedTable]);

  const orderClause = sort ? ` ORDER BY "${sort.column}" ${sort.dir.toUpperCase()}` : "";

  const dataQuery = useQuery({
    queryKey: ["table-rows", databaseId, selected, page, dataSearch, sort],
    enabled: selected !== null,
    queryFn: () =>
      runSql(
        organizationId,
        projectId,
        databaseId,
        `SELECT * FROM "${selected}"${whereClause}${orderClause} LIMIT ${PAGE_SIZE} OFFSET ${page * PAGE_SIZE};`
      ),
  });

  const countQuery = useQuery({
    queryKey: ["table-count", databaseId, selected, dataSearch],
    enabled: selected !== null,
    queryFn: async () => {
      const res = await runSql(
        organizationId,
        projectId,
        databaseId,
        `SELECT COUNT(*) FROM "${selected}"${whereClause};`
      );
      const value = res.rows[0]?.[0];
      return typeof value === "number" ? value : Number(value) || 0;
    },
  });

  const result = dataQuery.data;
  const rowCount = countQuery.data ?? null;
  const loading = dataQuery.isFetching || countQuery.isFetching;
  const error = dataQuery.error instanceof Error ? dataQuery.error.message : null;

  // Selection/editing state is keyed by row index into the current page's
  // result set, so it's meaningless once the underlying query changes — reset
  // it during render (React's documented pattern for this) rather than in a
  // post-commit effect.
  const resultKey = `${selected ?? ""}|${page}|${dataSearch}|${sort?.column ?? ""}|${sort?.dir ?? ""}`;
  const [prevResultKey, setPrevResultKey] = useState(resultKey);
  if (resultKey !== prevResultKey) {
    setPrevResultKey(resultKey);
    setSelectedRows(new Set());
    setEditingCell(null);
  }

  function selectTable(name: string) {
    setSelected(name);
    setPage(0);
    setDataSearch("");
    setSort(null);
    setShowAddForm(false);
  }

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["table-rows", databaseId, selected] });
    queryClient.invalidateQueries({ queryKey: ["table-count", databaseId, selected] });
  }

  function toggleSort(column: string) {
    setPage(0);
    setSort((current) => {
      if (current?.column !== column) return { column, dir: "asc" };
      if (current.dir === "asc") return { column, dir: "desc" };
      return null;
    });
  }

  function toggleRow(i: number) {
    setSelectedRows((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  function toggleAllRows() {
    if (!result) return;
    setSelectedRows((prev) => (prev.size === result.rows.length ? new Set() : new Set(result.rows.map((_, i) => i))));
  }

  async function commitDelete() {
    if (!result || !selectedTable || selectedRows.size === 0) return;
    setDeleting(true);
    try {
      const conditions = Array.from(selectedRows).map(
        (i) => `(${buildRowWhere(pkColumns, result.columns, result.rows[i])})`
      );
      await runSql(
        organizationId,
        projectId,
        databaseId,
        `DELETE FROM "${selectedTable.name}" WHERE ${conditions.join(" OR ")};`
      );
      setConfirmDelete(false);
      setSelectedRows(new Set());
      refresh();
    } catch (err) {
      setCellError(err instanceof Error ? err.message : "Failed to delete row(s)");
      setConfirmDelete(false);
    } finally {
      setDeleting(false);
    }
  }

  async function commitCellEdit(rowIndex: number, column: string, raw: string) {
    if (!result || !selectedTable) return;
    const row = result.rows[rowIndex];
    const currentIdx = result.columns.indexOf(column);
    const current = currentIdx >= 0 ? row[currentIdx] : null;
    const nextValue = raw === "" ? null : raw;
    if (nextValue === current || (nextValue === null && current === null)) {
      setEditingCell(null);
      return;
    }
    setSavingCell(true);
    setCellError(null);
    try {
      const setClause = nextValue === null ? `"${column}" = NULL` : `"${column}" = '${escapeSqlString(nextValue)}'`;
      await runSql(
        organizationId,
        projectId,
        databaseId,
        `UPDATE "${selectedTable.name}" SET ${setClause} WHERE ${buildRowWhere(pkColumns, result.columns, row)};`
      );
      setEditingCell(null);
      refresh();
    } catch (err) {
      setCellError(err instanceof Error ? err.message : "Failed to update cell");
    } finally {
      setSavingCell(false);
    }
  }

  if (tables.length === 0) {
    return (
      <EmptyState
        icon={Table2}
        title="No tables found"
        description="This database may still be provisioning, or has no tables yet."
      />
    );
  }

  const from = rowCount === 0 ? 0 : page * PAGE_SIZE + 1;
  const to =
    rowCount === null ? page * PAGE_SIZE + (result?.rows.length ?? 0) : Math.min((page + 1) * PAGE_SIZE, rowCount);

  return (
    <div className="flex gap-4">
      <div className="w-56 shrink-0 space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
          <Input
            value={tableQuery}
            onChange={(e) => setTableQuery(e.target.value)}
            placeholder="Search tables..."
            className="h-9 pl-8 text-sm"
          />
        </div>
        <ul className="space-y-0.5">
          {filteredTables.map((table) => (
            <li key={table.name}>
              <button
                type="button"
                onClick={() => selectTable(table.name)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm",
                  table.name === selected
                    ? "bg-slate-800 font-medium text-slate-100"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100"
                )}
              >
                <Table2 className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                <span className="truncate">{table.name}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="min-w-0 flex-1">
        {!selected || !selectedTable ? (
          <p className="text-sm text-slate-500">Select a table.</p>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" onClick={refresh} disabled={loading} className="h-9 w-9 p-0">
                <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
              </Button>
              <div className="relative flex-1 sm:max-w-xs">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                <Input
                  value={dataSearch}
                  onChange={(e) => {
                    setDataSearch(e.target.value);
                    setPage(0);
                  }}
                  placeholder="Search rows..."
                  className="h-9 pl-8 text-sm"
                />
              </div>
              {selectedRows.size > 0 ? (
                <Button
                  onClick={() => setConfirmDelete(true)}
                  className="h-9 bg-red-600 text-white hover:bg-red-500"
                >
                  <Trash2 className="mr-1.5 h-4 w-4" />
                  Delete {selectedRows.size} row{selectedRows.size > 1 ? "s" : ""}
                </Button>
              ) : (
                <Button onClick={() => setShowAddForm((v) => !v)} className="h-9">
                  <Plus className="mr-1.5 h-4 w-4" />
                  Add record
                </Button>
              )}
              <div className="ml-auto flex items-center gap-2 text-sm text-slate-500">
                <span>
                  {from}-{to} of {rowCount ?? "…"}
                </span>
                <Button
                  variant="outline"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0 || loading}
                  className="h-8 w-8 p-0"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={loading || (rowCount !== null && to >= rowCount)}
                  className="h-8 w-8 p-0"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {!editable && (
              <p className="text-xs text-slate-500">
                This table has no primary key, so rows can&apos;t be selected, edited, or deleted individually.
              </p>
            )}
            {cellError && <p className="text-sm text-red-400">{cellError}</p>}

            {showAddForm && (
              <AddRecordForm
                table={selectedTable}
                onCancel={() => setShowAddForm(false)}
                onSubmit={async (values) => {
                  const columns = Object.keys(values);
                  const insertSql =
                    columns.length === 0
                      ? `INSERT INTO "${selectedTable.name}" DEFAULT VALUES;`
                      : `INSERT INTO "${selectedTable.name}" (${columns.map((c) => `"${c}"`).join(", ")}) VALUES (${columns.map((c) => `'${escapeSqlString(values[c])}'`).join(", ")});`;
                  await runSql(organizationId, projectId, databaseId, insertSql);
                  setShowAddForm(false);
                  refresh();
                }}
              />
            )}

            {error ? (
              <p className="text-sm text-red-400">{error}</p>
            ) : result && result.columns.length > 0 ? (
              <div className="overflow-x-auto rounded-md border border-slate-800">
                <table className="min-w-full divide-y divide-slate-800 text-sm">
                  <thead className="bg-slate-950/60">
                    <tr>
                      {editable && (
                        <th className="w-10 px-3 py-2">
                          <input
                            type="checkbox"
                            checked={result.rows.length > 0 && selectedRows.size === result.rows.length}
                            onChange={toggleAllRows}
                            className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900 accent-emerald-600"
                            aria-label="Select all rows"
                          />
                        </th>
                      )}
                      {result.columns.map((col) => {
                        const colType = selectedTable.columns.find((c) => c.name === col)?.type;
                        return (
                          <th key={col} className="whitespace-nowrap px-0 py-0 text-left">
                            <button
                              type="button"
                              onClick={() => toggleSort(col)}
                              className="flex w-full items-center gap-1.5 px-3 py-2 text-xs font-medium uppercase tracking-wide text-slate-500 hover:text-slate-200"
                            >
                              {col}
                              {colType && (
                                <span className="lowercase text-slate-600">{colType}</span>
                              )}
                              {sort?.column === col ? (
                                sort.dir === "asc" ? (
                                  <ArrowUp className="h-3 w-3" />
                                ) : (
                                  <ArrowDown className="h-3 w-3" />
                                )
                              ) : (
                                <ArrowUpDown className="h-3 w-3 text-slate-700" />
                              )}
                            </button>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {result.rows.map((row, i) => (
                      <tr key={i} className={cn("hover:bg-slate-800/40", selectedRows.has(i) && "bg-slate-800/60")}>
                        {editable && (
                          <td className="w-10 px-3 py-2">
                            <input
                              type="checkbox"
                              checked={selectedRows.has(i)}
                              onChange={() => toggleRow(i)}
                              className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900 accent-emerald-600"
                              aria-label={`Select row ${i + 1}`}
                            />
                          </td>
                        )}
                        {row.map((cell, j) => {
                          const column = result.columns[j];
                          const isEditing = editingCell?.row === i && editingCell?.column === column;
                          return (
                            <td
                              key={j}
                              onDoubleClick={() => editable && setEditingCell({ row: i, column })}
                              className={cn(
                                "whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-300",
                                editable && "cursor-text"
                              )}
                            >
                              {isEditing ? (
                                <EditableCell
                                  initialValue={cell === null ? "" : String(cell)}
                                  disabled={savingCell}
                                  onCommit={(value) => commitCellEdit(i, column, value)}
                                  onCancel={() => setEditingCell(null)}
                                />
                              ) : cell === null ? (
                                <span className="text-slate-600">null</span>
                              ) : (
                                String(cell)
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                    {result.rows.length === 0 && (
                      <tr>
                        <td
                          colSpan={result.columns.length + (editable ? 1 : 0)}
                          className="px-3 py-6 text-center text-slate-500"
                        >
                          No rows.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-slate-500">{loading ? "Loading…" : "No data."}</p>
            )}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${selectedRows.size} row${selectedRows.size > 1 ? "s" : ""}?`}
        description="This permanently deletes the selected row(s) from the table. This can't be undone."
        confirmLabel="Delete"
        pending={deleting}
        onConfirm={commitDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}

function EditableCell({
  initialValue,
  disabled,
  onCommit,
  onCancel,
}: {
  initialValue: string;
  disabled: boolean;
  onCommit: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initialValue);

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      onCommit(value);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    }
  }

  return (
    <input
      autoFocus
      value={value}
      disabled={disabled}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={handleKeyDown}
      onBlur={() => onCommit(value)}
      className="w-full min-w-[6rem] rounded border border-emerald-600 bg-slate-950 px-1.5 py-0.5 font-mono text-xs text-slate-100 outline-none"
    />
  );
}

function AddRecordForm({
  table,
  onSubmit,
  onCancel,
}: {
  table: TableInfo;
  onSubmit: (values: Record<string, string>) => Promise<void>;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      // A blank field is omitted from the INSERT entirely (not sent as NULL)
      // so columns with a default — most commonly a SERIAL/IDENTITY primary
      // key, which schema introspection still reports as NOT NULL — fall
      // back to their default instead of forcing the user to type a value.
      const payload: Record<string, string> = {};
      for (const col of table.columns) {
        const raw = values[col.name];
        if (raw !== undefined && raw !== "") payload[col.name] = raw;
      }
      await onSubmit(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to insert row");
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <CardContent className="py-4">
        <form onSubmit={handleSubmit} className="space-y-3">
          {error && <p className="text-sm text-red-400">{error}</p>}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {table.columns.map((col) => (
              <div key={col.name}>
                <Label htmlFor={`field-${col.name}`}>
                  {col.name}
                  <span className="ml-1 font-mono text-xs font-normal text-slate-500">{col.type}</span>
                </Label>
                <Input
                  id={`field-${col.name}`}
                  value={values[col.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [col.name]: e.target.value }))}
                  placeholder={col.nullable ? "NULL" : "default / required"}
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={pending}>
              {pending ? "Inserting…" : "Insert row"}
            </Button>
            <Button type="button" variant="outline" onClick={onCancel} disabled={pending}>
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
