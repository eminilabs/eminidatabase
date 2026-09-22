"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { DatabaseResponse } from "@eminidatabase/sdk";
import { Database as DatabaseIcon, Pause, Play, SlidersHorizontal } from "lucide-react";
import { useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { resumeDatabaseAction, suspendDatabaseAction } from "./actions";
import { DeleteDatabaseButton } from "./delete-database-button";
import { ResizeDatabaseForm } from "./resize-database-form";

const STABLE_STATUSES = new Set(["running", "suspended", "failed", "deleted"]);

async function fetchDatabase(
  organizationId: string,
  projectId: string,
  databaseId: string
): Promise<DatabaseResponse> {
  const res = await fetch(`/api/organizations/${organizationId}/projects/${projectId}/databases/${databaseId}`);
  if (!res.ok) throw new Error("Failed to load database status");
  return res.json();
}

export function DatabaseHeader({
  organizationId,
  projectId,
  databaseId,
  initialDatabase,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  initialDatabase: DatabaseResponse;
}) {
  const [resizeOpen, setResizeOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const queryKey = ["database", databaseId];
  const { data: database } = useQuery({
    queryKey,
    queryFn: () => fetchDatabase(organizationId, projectId, databaseId),
    initialData: initialDatabase,
    // Keep polling while the database is transitioning (suspending/updating/
    // etc.) so Suspend/Resume/Resize become available again as soon as the
    // real job — dispatched by app/worker.py — actually settles, instead of
    // requiring a manual page reload.
    refetchInterval: (query) => (STABLE_STATUSES.has(query.state.data?.status ?? "") ? false : 2000),
  });

  const status = database?.status ?? initialDatabase.status;
  const name = database?.name ?? initialDatabase.name;

  function refresh() {
    queryClient.invalidateQueries({ queryKey });
  }

  function handleSuspend() {
    startTransition(async () => {
      const result = await suspendDatabaseAction(organizationId, projectId, databaseId);
      setError(result?.error ?? null);
      refresh();
    });
  }

  function handleResume() {
    startTransition(async () => {
      const result = await resumeDatabaseAction(organizationId, projectId, databaseId);
      setError(result?.error ?? null);
      refresh();
    });
  }

  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white">
          <DatabaseIcon className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{name}</h1>
          <StatusBadge status={status} className="mt-0.5" />
        </div>
      </div>
      <div className="flex flex-col items-end gap-2">
        {error && <Alert>{error}</Alert>}
        <div className="flex items-center gap-2">
          {status === "running" && (
            <>
              <Button variant="outline" onClick={() => setResizeOpen(true)} disabled={pending}>
                <SlidersHorizontal className="mr-1.5 h-4 w-4" />
                Resize
              </Button>
              <Button variant="outline" onClick={handleSuspend} disabled={pending}>
                <Pause className="mr-1.5 h-4 w-4" />
                Suspend
              </Button>
            </>
          )}
          {status === "suspended" && (
            <Button variant="outline" onClick={handleResume} disabled={pending}>
              <Play className="mr-1.5 h-4 w-4" />
              Resume
            </Button>
          )}
          <DeleteDatabaseButton
            organizationId={organizationId}
            projectId={projectId}
            databaseId={databaseId}
            databaseName={name}
          />
        </div>
      </div>

      <ResizeDatabaseForm
        organizationId={organizationId}
        projectId={projectId}
        databaseId={databaseId}
        open={resizeOpen}
        onClose={() => setResizeOpen(false)}
        onResized={refresh}
        current={{
          cpuLimit: database?.cpu_limit ?? initialDatabase.cpu_limit,
          ramLimitMb: database?.ram_limit_mb ?? initialDatabase.ram_limit_mb,
          storageLimitGb: database?.storage_limit_gb ?? initialDatabase.storage_limit_gb,
        }}
      />
    </div>
  );
}
