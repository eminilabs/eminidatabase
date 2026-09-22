"use client";

import { useActionState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Modal } from "@/components/ui/modal";

import { resizeDatabaseAction, type ResizeFormState } from "./actions";

export function ResizeDatabaseForm({
  organizationId,
  projectId,
  databaseId,
  open,
  onClose,
  onResized,
  current,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  open: boolean;
  onClose: () => void;
  onResized: () => void;
  current: { cpuLimit: number; ramLimitMb: number; storageLimitGb: number };
}) {
  const action = resizeDatabaseAction.bind(null, organizationId, projectId, databaseId);
  const [state, formAction, pending] = useActionState<ResizeFormState, FormData>(
    async (prevState, formData) => {
      const result = await action(prevState, formData);
      if (!result?.error) {
        onResized();
        onClose();
      }
      return result;
    },
    undefined
  );

  return (
    <Modal open={open} title="Resize database" onClose={onClose}>
      <form action={formAction} className="space-y-4">
        {state?.error && <Alert>{state.error}</Alert>}
        <p className="text-sm text-slate-400">
          Vertical resize is applied immediately — the database must be running.
        </p>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <Label htmlFor="cpu_limit">vCPU</Label>
            <Input
              id="cpu_limit"
              name="cpu_limit"
              type="number"
              min={1}
              step={1}
              defaultValue={current.cpuLimit}
              required
            />
          </div>
          <div>
            <Label htmlFor="ram_limit_mb">RAM (MB)</Label>
            <Input
              id="ram_limit_mb"
              name="ram_limit_mb"
              type="number"
              min={256}
              step={256}
              defaultValue={current.ramLimitMb}
              required
            />
          </div>
          <div>
            <Label htmlFor="storage_limit_gb">Storage (GB)</Label>
            <Input
              id="storage_limit_gb"
              name="storage_limit_gb"
              type="number"
              min={1}
              step={1}
              defaultValue={current.storageLimitGb}
              required
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Button type="submit" disabled={pending}>
            {pending ? "Resizing…" : "Resize"}
          </Button>
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}
