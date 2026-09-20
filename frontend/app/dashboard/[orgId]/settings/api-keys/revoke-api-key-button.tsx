"use client";

import { useTransition } from "react";

import { Button } from "@/components/ui/button";

import { revokeApiKeyAction } from "./actions";

export function RevokeApiKeyButton({
  organizationId,
  apiKeyId,
}: {
  organizationId: string;
  apiKeyId: string;
}) {
  const [pending, startTransition] = useTransition();
  return (
    <Button
      variant="ghost"
      disabled={pending}
      onClick={() => startTransition(() => revokeApiKeyAction(organizationId, apiKeyId))}
    >
      {pending ? "Revoking…" : "Revoke"}
    </Button>
  );
}
