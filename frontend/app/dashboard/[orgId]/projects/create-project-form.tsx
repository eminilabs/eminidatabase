"use client";

import { useActionState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { createProjectAction } from "./actions";

export function CreateProjectForm({ organizationId }: { organizationId: string }) {
  const boundAction = createProjectAction.bind(null, organizationId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  return (
    <form action={action} className="flex flex-wrap items-end gap-3">
      {state?.error && (
        <div className="w-full">
          <Alert>{state.error}</Alert>
        </div>
      )}
      <div>
        <Label htmlFor="name">Name</Label>
        <Input id="name" name="name" required placeholder="Shop" className="w-48" />
      </div>
      <div>
        <Label htmlFor="slug">Slug</Label>
        <Input id="slug" name="slug" required placeholder="shop" pattern="[a-z0-9\-]+" className="w-48" />
      </div>
      <Button type="submit" disabled={pending}>
        {pending ? "Creating…" : "Create project"}
      </Button>
    </form>
  );
}
