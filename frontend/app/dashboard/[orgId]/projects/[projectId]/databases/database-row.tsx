"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import type { DatabaseResponse } from "@eminidatabase/sdk";
import { Card, CardContent } from "@/components/ui/card";

const TERMINAL_STATUSES = new Set(["running", "failed", "deleted"]);

const STATUS_STYLES: Record<string, string> = {
  running: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  creating: "bg-amber-100 text-amber-800",
};

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

  return (
    <Link href={`/dashboard/${organizationId}/projects/${projectId}/databases/${initialDatabase.id}`}>
      <Card className="transition-shadow hover:shadow-md">
        <CardContent className="flex items-center justify-between py-4">
          <div>
            <p className="font-medium text-slate-900">{database?.name ?? initialDatabase.name}</p>
            <p className="text-sm text-slate-500">
              {database?.cpu_limit ?? initialDatabase.cpu_limit} vCPU ·{" "}
              {database?.storage_limit_gb ?? initialDatabase.storage_limit_gb} GB
            </p>
          </div>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              STATUS_STYLES[status] ?? "bg-slate-100 text-slate-700"
            }`}
          >
            {status}
          </span>
        </CardContent>
      </Card>
    </Link>
  );
}
