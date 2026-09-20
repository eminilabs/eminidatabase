"use client";

import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";

import { deleteRoleAction, rotateRoleAction } from "./actions";

export function RoleRowActions({
  organizationId,
  projectId,
  databaseId,
  credentialId,
  isPrimary,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
  credentialId: string;
  isPrimary: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [rotated, setRotated] = useState<string | null>(null);

  if (rotated) {
    return <span className="font-mono text-xs text-amber-700">New password: {rotated}</span>;
  }

  return (
    <div className="flex gap-2">
      <Button
        variant="ghost"
        disabled={pending}
        onClick={() =>
          startTransition(async () => {
            const result = await rotateRoleAction(organizationId, projectId, databaseId, credentialId);
            setRotated(result.password);
          })
        }
      >
        Rotate
      </Button>
      {!isPrimary && (
        <Button
          variant="ghost"
          disabled={pending}
          onClick={() =>
            startTransition(() => deleteRoleAction(organizationId, projectId, databaseId, credentialId))
          }
        >
          Delete
        </Button>
      )}
    </div>
  );
}
