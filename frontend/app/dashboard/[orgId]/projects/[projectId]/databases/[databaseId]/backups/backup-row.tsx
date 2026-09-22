"use client";

import { useQuery } from "@tanstack/react-query";
import { useActionState, useState } from "react";

import type { BackupResponse } from "@eminidatabase/sdk";
import { Alert } from "@/components/ui/alert";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

import { restoreBackupAction } from "./actions";

const TERMINAL_STATUSES = new Set(["completed", "failed", "verified", "verification_failed"]);
const RESTORABLE_STATUSES = new Set(["completed", "verified"]);

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

export function BackupRow({
  organizationId,
  projectId,
  databaseId,
  initialBackup,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  initialBackup: BackupResponse;
}) {
  const [showRestore, setShowRestore] = useState(false);
  const boundRestore = restoreBackupAction.bind(
    null,
    organizationId,
    projectId,
    databaseId,
    initialBackup.id
  );
  const [state, action, pending] = useActionState(boundRestore, undefined);

  const { data: backup } = useQuery({
    queryKey: ["backup", initialBackup.id],
    queryFn: async (): Promise<BackupResponse> => {
      const res = await fetch(
        `/api/organizations/${organizationId}/projects/${projectId}/databases/${databaseId}/backups/${initialBackup.id}`
      );
      if (!res.ok) throw new Error("Failed to load backup status");
      return res.json();
    },
    initialData: initialBackup,
    refetchInterval: (query) => (TERMINAL_STATUSES.has(query.state.data?.status ?? "") ? false : 3000),
  });

  const status = backup?.status ?? initialBackup.status;

  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-slate-100">
              {backup?.type ?? initialBackup.type} · {formatBytes(backup?.size_bytes ?? null)}
            </p>
            <p className="text-xs text-slate-500">
              {new Date(backup?.created_at ?? initialBackup.created_at).toLocaleString()}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={status} />
            {RESTORABLE_STATUSES.has(status) && (
              <Button variant="outline" onClick={() => setShowRestore((v) => !v)}>
                Restore
              </Button>
            )}
          </div>
        </div>

        {showRestore && (
          <form action={action} className="flex items-end gap-2">
            {state?.error && (
              <div className="w-full">
                <Alert>{state.error}</Alert>
              </div>
            )}
            <Input
              name="name"
              placeholder="restored-database-name"
              required
              pattern="[a-z][a-z0-9\-]{1,62}"
              minLength={2}
              maxLength={63}
              title="Start with a lowercase letter, then lowercase letters, numbers, or hyphens"
              className="w-64"
            />
            <Button type="submit" disabled={pending}>
              {pending ? "Restoring…" : "Restore to a new database"}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
