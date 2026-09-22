"use client";

import { Trash2 } from "lucide-react";
import { useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

import { deleteProjectAction } from "../../actions";

export function DeleteProjectButton({
  organizationId,
  projectId,
  projectName,
}: {
  organizationId: string;
  projectId: string;
  projectName: string;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleConfirm() {
    startTransition(async () => {
      const result = await deleteProjectAction(organizationId, projectId);
      // On success the action redirects (throwing internally) and this line
      // is never reached; it only runs when deletion was rejected.
      if (result?.error) {
        setError(result.error);
        setOpen(false);
      }
    });
  }

  return (
    <div>
      {error && <Alert className="mb-2">{error}</Alert>}
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Trash2 className="mr-1.5 h-4 w-4" />
        Delete project
      </Button>
      <ConfirmDialog
        open={open}
        title={`Delete project "${projectName}"?`}
        description="This cannot be undone. All databases in this project must be deleted first."
        confirmLabel="Delete project"
        pending={pending}
        onConfirm={handleConfirm}
        onCancel={() => setOpen(false)}
      />
    </div>
  );
}
