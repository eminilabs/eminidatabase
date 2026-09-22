"use client";

import { useActionState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { createWebhookAction } from "./actions";

// Mirrors backend/app/models/webhook.py's SUPPORTED_EVENT_TYPES.
const EVENT_TYPES = [
  "database.created",
  "database.failed",
  "backup.completed",
  "backup.failed",
  "restore.completed",
  "invoice.paid",
];

export function CreateWebhookForm({ organizationId }: { organizationId: string }) {
  const boundAction = createWebhookAction.bind(null, organizationId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  if (state?.created) {
    return (
      <Alert className="border-amber-900 bg-amber-950/40 text-amber-300">
        Webhook for {state.created.url} created. Signing secret (shown once, copy it now):{" "}
        <span className="font-mono">{state.created.secret}</span>
      </Alert>
    );
  }

  return (
    <form action={action} className="space-y-3">
      {state?.error && <Alert>{state.error}</Alert>}
      <div>
        <Label htmlFor="url">URL</Label>
        <Input id="url" name="url" type="url" required placeholder="https://example.com/hooks" />
      </div>
      <div>
        <Label>Events</Label>
        <div className="flex flex-wrap gap-3 text-sm">
          {EVENT_TYPES.map((type) => (
            <label key={type} className="flex items-center gap-1.5">
              <input type="checkbox" name="event_types" value={type} className="h-4 w-4" />
              {type}
            </label>
          ))}
        </div>
      </div>
      <Button type="submit" disabled={pending}>
        {pending ? "Creating…" : "Create webhook"}
      </Button>
    </form>
  );
}
