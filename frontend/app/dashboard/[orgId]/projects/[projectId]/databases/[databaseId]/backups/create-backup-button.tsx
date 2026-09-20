"use client";

import { useTransition } from "react";

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
  return (
    <Button
      disabled={pending}
      onClick={() => startTransition(() => createBackupAction(organizationId, projectId, databaseId))}
    >
      {pending ? "Starting…" : "Back up now"}
    </Button>
  );
}
