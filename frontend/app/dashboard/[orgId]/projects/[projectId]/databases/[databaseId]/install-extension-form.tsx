"use client";

import { useActionState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { installExtensionAction } from "./actions";

export function InstallExtensionForm({
  organizationId,
  projectId,
  databaseId,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
}) {
  const boundAction = installExtensionAction.bind(null, organizationId, projectId, databaseId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  return (
    <form action={action} className="flex items-end gap-2">
      {state?.error && (
        <div className="w-full">
          <Alert>{state.error}</Alert>
        </div>
      )}
      <Input name="name" placeholder="pg_trgm" required className="w-48" />
      <Button type="submit" variant="outline" disabled={pending}>
        {pending ? "Installing…" : "Install"}
      </Button>
    </form>
  );
}
