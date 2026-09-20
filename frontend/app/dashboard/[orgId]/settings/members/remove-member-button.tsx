"use client";

import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";

import { removeMemberAction } from "./actions";

export function RemoveMemberButton({
  organizationId,
  targetUserId,
}: {
  organizationId: string;
  targetUserId: string;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="text-right">
      <Button
        variant="ghost"
        disabled={pending}
        onClick={() =>
          startTransition(async () => {
            const result = await removeMemberAction(organizationId, targetUserId);
            setError(result?.error ?? null);
          })
        }
      >
        {pending ? "Removing…" : "Remove"}
      </Button>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
