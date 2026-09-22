"use client";

import type { DatabaseResponse, RegionResponse } from "@eminidatabase/sdk";
import { Database as DatabaseIcon, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";

import { CreateDatabaseForm } from "./create-database-form";
import { DatabaseRow } from "./database-row";
import { DeleteProjectButton } from "./delete-project-button";

export function DatabasesView({
  organizationId,
  projectId,
  projectName,
  databases,
  regions,
}: {
  organizationId: string;
  projectId: string;
  projectName: string;
  databases: DatabaseResponse[];
  regions: RegionResponse[];
}) {
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return databases;
    return databases.filter((d) => d.name.toLowerCase().includes(q));
  }, [databases, query]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{projectName}</h1>
          <p className="mt-1 text-sm text-slate-500">Databases in this project.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => setCreating((v) => !v)} disabled={regions.length === 0}>
            <Plus className="mr-1.5 h-4 w-4" />
            New database
          </Button>
          <DeleteProjectButton organizationId={organizationId} projectId={projectId} projectName={projectName} />
        </div>
      </div>

      {creating && (
        <Card>
          <CardContent className="py-4">
            <CreateDatabaseForm organizationId={organizationId} projectId={projectId} regions={regions} />
          </CardContent>
        </Card>
      )}

      {databases.length === 0 ? (
        <EmptyState icon={DatabaseIcon} title="No databases yet" description="Create one above to get started." />
      ) : (
        <>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search databases..."
              className="pl-9"
            />
          </div>
          <div className="space-y-3">
            {filtered.map((database) => (
              <DatabaseRow
                key={database.id}
                organizationId={organizationId}
                projectId={projectId}
                initialDatabase={database}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
