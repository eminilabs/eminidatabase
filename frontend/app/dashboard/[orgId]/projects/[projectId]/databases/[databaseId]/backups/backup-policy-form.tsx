"use client";

import { useActionState } from "react";

import type { BackupPolicyUpdate } from "@eminidatabase/sdk";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { setBackupPolicyAction } from "./actions";

export function BackupPolicyForm({
  organizationId,
  projectId,
  databaseId,
  policy,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  policy: BackupPolicyUpdate;
}) {
  const boundAction = setBackupPolicyAction.bind(null, organizationId, projectId, databaseId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  return (
    <form action={action} className="flex flex-wrap items-end gap-4">
      {state?.error && (
        <div className="w-full">
          <Alert>{state.error}</Alert>
        </div>
      )}
      {state?.success && (
        <div className="w-full">
          <Alert className="border-green-200 bg-green-50 text-green-800">Policy updated.</Alert>
        </div>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="enabled" defaultChecked={policy.enabled} className="h-4 w-4" />
        Automatic backups enabled
      </label>
      <div>
        <Label htmlFor="frequency_hours">Frequency (hours)</Label>
        <Input
          id="frequency_hours"
          name="frequency_hours"
          type="number"
          min={1}
          defaultValue={policy.frequency_hours}
          className="w-32"
        />
      </div>
      <div>
        <Label htmlFor="retention_days">Retention (days)</Label>
        <Input
          id="retention_days"
          name="retention_days"
          type="number"
          min={1}
          defaultValue={policy.retention_days}
          className="w-32"
        />
      </div>
      <Button type="submit" variant="outline" disabled={pending}>
        {pending ? "Saving…" : "Save policy"}
      </Button>
    </form>
  );
}
