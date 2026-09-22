"use client";

import { useQuery } from "@tanstack/react-query";
import { Database as DatabaseIcon } from "lucide-react";
import Link from "next/link";

import type { DatabaseResponse } from "@eminidatabase/sdk";
import { StatusBadge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const TERMINAL_STATUSES = new Set(["running", "failed", "deleted"]);

export function DatabaseRow({
  organizationId,
  projectId,
  initialDatabase,
}: {
  organizationId: string;
  projectId: string;
  initialDatabase: DatabaseResponse;
}) {
  const { data: database } = useQuery({
    queryKey: ["database", initialDatabase.id],
    queryFn: async (): Promise<DatabaseResponse> => {
      const res = await fetch(
        `/api/organizations/${organizationId}/projects/${projectId}/databases/${initialDatabase.id}`
      );
      if (!res.ok) throw new Error("Failed to load database status");
      return res.json();
    },
    initialData: initialDatabase,
    // Only keep polling while the database is mid-provisioning — matches the
    // async-job UX every mutating database/backup endpoint in this API uses
    // (cf. app/dashboard/[orgId]/projects/[projectId]/databases/actions.ts).
    refetchInterval: (query) =>
      TERMINAL_STATUSES.has(query.state.data?.status ?? "") ? false : 2000,
  });

  const status = database?.status ?? initialDatabase.status;

  // The list endpoint only excludes DELETED, not the DELETING state a
  // deletion job passes through first — so this row keeps showing (with a
  // live status badge) until the async job actually finishes, then hides
  // itself rather than waiting for a full page reload to disappear.
  if (status === "deleted") return null;

  return (
    <Link href={`/dashboard/${organizationId}/projects/${projectId}/databases/${initialDatabase.id}`}>
      <Card className="transition-shadow hover:shadow-md">
        <CardContent className="flex items-center justify-between py-4">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-800 text-slate-500">
              <DatabaseIcon className="h-4 w-4" />
            </span>
            <div>
              <p className="font-medium text-slate-100">{database?.name ?? initialDatabase.name}</p>
              <p className="text-sm text-slate-500">
                {database?.cpu_limit ?? initialDatabase.cpu_limit} vCPU ·{" "}
                {database?.storage_limit_gb ?? initialDatabase.storage_limit_gb} GB
              </p>
            </div>
          </div>
          <StatusBadge status={status} />
        </CardContent>
      </Card>
    </Link>
  );
}
