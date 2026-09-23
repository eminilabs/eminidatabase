"use client";

import type { DatabaseResponse, ProjectResponse } from "@eminidatabase/sdk";
import { Database as DatabaseIcon, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { DatabaseRow } from "@/app/dashboard/[orgId]/projects/[projectId]/databases/database-row";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";

export type OrgDatabaseRow = { project: ProjectResponse; database: DatabaseResponse };

export function OrgDatabasesView({
  organizationId,
  rows,
}: {
  organizationId: string;
  rows: OrgDatabaseRow[];
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      ({ database, project }) =>
        database.name.toLowerCase().includes(q) || project.name.toLowerCase().includes(q)
    );
  }, [rows, query]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-100">Databases</h1>
        <p className="mt-1 text-sm text-slate-500">Every database across all projects in this organization.</p>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={DatabaseIcon}
          title="No databases yet"
          description="Create a project, then a database inside it, to see it here."
        />
      ) : (
        <>
          <div className="relative max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search databases..."
              className="pl-9"
            />
          </div>

          <div className="space-y-3">
            {filtered.map(({ project, database }) => (
              <div key={database.id}>
                <p className="mb-1 px-1 text-xs font-medium uppercase tracking-wide text-slate-600">
                  {project.name}
                </p>
                <DatabaseRow
                  organizationId={organizationId}
                  projectId={project.id}
                  initialDatabase={database}
                />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
