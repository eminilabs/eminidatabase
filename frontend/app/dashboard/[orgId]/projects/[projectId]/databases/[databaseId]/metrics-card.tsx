"use client";

import { useQuery } from "@tanstack/react-query";

import type { DatabaseMetricsResponse } from "@eminidatabase/sdk";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function formatBytes(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function MetricsCard({
  organizationId,
  projectId,
  databaseId,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
}) {
  const { data, error } = useQuery({
    queryKey: ["database-metrics", databaseId],
    queryFn: async (): Promise<DatabaseMetricsResponse> => {
      const res = await fetch(
        `/api/organizations/${organizationId}/projects/${projectId}/databases/${databaseId}/metrics`
      );
      if (!res.ok) throw new Error("unavailable");
      return res.json();
    },
    refetchInterval: 10_000,
    retry: false,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Metrics</CardTitle>
      </CardHeader>
      <CardContent>
        {error || !data ? (
          <p className="text-sm text-slate-500">
            Metrics unavailable — the database may not be running.
          </p>
        ) : (
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Size</p>
              <p className="text-lg font-semibold text-slate-100">{formatBytes(data.size_bytes)}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Connections</p>
              <p className="text-lg font-semibold text-slate-100">
                {data.active_connections} / {data.max_connections}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
