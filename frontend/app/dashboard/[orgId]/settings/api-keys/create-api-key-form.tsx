"use client";

import { useActionState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { createApiKeyAction } from "./actions";

export function CreateApiKeyForm({ organizationId }: { organizationId: string }) {
  const boundAction = createApiKeyAction.bind(null, organizationId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  if (state?.created) {
    return (
      <Alert className="border-amber-900 bg-amber-950/40 text-amber-300">
        Key <span className="font-mono">{state.created.apiKey}</span> created (shown once, copy it
        now).
      </Alert>
    );
  }

  return (
    <form action={action} className="flex items-end gap-2">
      {state?.error && (
        <div className="w-full">
          <Alert>{state.error}</Alert>
        </div>
      )}
      <Input name="name" placeholder="CI pipeline" required className="w-56" />
      <Button type="submit" disabled={pending}>
        {pending ? "Creating…" : "Create key"}
      </Button>
    </form>
  );
}
