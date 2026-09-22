"use client";

import { useActionState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { createRoleAction } from "./actions";

export function CreateRoleForm({
  organizationId,
  projectId,
  databaseId,
}: {
  organizationId: string;
  projectId: string;
  databaseId: string;
}) {
  const boundAction = createRoleAction.bind(null, organizationId, projectId, databaseId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  if (state?.created) {
    return (
      <Alert className="border-amber-900 bg-amber-950/40 text-amber-300">
        Role <span className="font-mono">{state.created.roleName}</span> created. Password (shown
        once, copy it now): <span className="font-mono">{state.created.password}</span>
      </Alert>
    );
  }

  return (
    <form action={action} className="flex flex-wrap items-end gap-2">
      {state?.error && (
        <div className="w-full">
          <Alert>{state.error}</Alert>
        </div>
      )}
      <div>
        <Label htmlFor="role-name">Name</Label>
        <Input id="role-name" name="name" required placeholder="reporting" className="w-40" />
      </div>
      <div>
        <Label htmlFor="role-scope">Scope</Label>
        <select
          id="role-scope"
          name="scope"
          className="flex h-10 w-32 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
        >
          <option value="app">app</option>
          <option value="readonly">readonly</option>
        </select>
      </div>
      <Button type="submit" variant="outline" disabled={pending}>
        {pending ? "Creating…" : "Create role"}
      </Button>
    </form>
  );
}
