"use client";

import { Trash2 } from "lucide-react";
import { useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

import { deleteDatabaseAction } from "../actions";

export function DeleteDatabaseButton({
  organizationId,
  projectId,
  databaseId,
  databaseName,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  databaseName: string;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleConfirm() {
    startTransition(async () => {
      const result = await deleteDatabaseAction(organizationId, projectId, databaseId);
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
        Delete
      </Button>
      <ConfirmDialog
        open={open}
        title={`Delete database "${databaseName}"?`}
        description="This cannot be undone. The database and its data will be permanently removed."
        confirmLabel="Delete database"
        pending={pending}
        onConfirm={handleConfirm}
        onCancel={() => setOpen(false)}
      />
    </div>
  );
}
