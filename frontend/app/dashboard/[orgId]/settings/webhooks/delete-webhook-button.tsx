"use client";

import { useTransition } from "react";

import { Button } from "@/components/ui/button";

import { deleteWebhookAction } from "./actions";

export function DeleteWebhookButton({
  organizationId,
  webhookId,
}: {
  organizationId: string;
  webhookId: string;
}) {
  const [pending, startTransition] = useTransition();
  return (
    <Button
      variant="ghost"
      disabled={pending}
      onClick={() => startTransition(() => deleteWebhookAction(organizationId, webhookId))}
    >
      {pending ? "Deleting…" : "Delete"}
    </Button>
  );
}
