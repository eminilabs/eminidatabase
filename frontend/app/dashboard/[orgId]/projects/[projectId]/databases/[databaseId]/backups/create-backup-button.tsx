"use client";

import { useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { createBackupAction } from "./actions";

export function CreateBackupButton({
  organizationId,
  projectId,
  databaseId,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function handleClick() {
    startTransition(async () => {
      const result = await createBackupAction(organizationId, projectId, databaseId);
      setError(result?.error ?? null);
    });
  }

  return (
    <div>
      {error && <Alert className="mb-2">{error}</Alert>}
      <Button disabled={pending} onClick={handleClick}>
        {pending ? "Starting…" : "Back up now"}
      </Button>
    </div>
  );
}
