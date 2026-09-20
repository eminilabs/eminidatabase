"use client";

import { useTransition } from "react";

import { Button } from "@/components/ui/button";

import { dropExtensionAction } from "./actions";

export function DropExtensionButton({
  organizationId,
  projectId,
  databaseId,
  name,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  name: string;
}) {
  const [pending, startTransition] = useTransition();
  return (
    <Button
      variant="ghost"
      disabled={pending}
      onClick={() =>
        startTransition(() => dropExtensionAction(organizationId, projectId, databaseId, name))
      }
    >
      {pending ? "Dropping…" : "Drop"}
    </Button>
  );
}
