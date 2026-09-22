"use client";

import { useActionState } from "react";

import type { RegionResponse } from "@eminidatabase/sdk";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { createDatabaseAction } from "./actions";

export function CreateDatabaseForm({
  organizationId,
  projectId,
  regions,
}: {
  organizationId: string;
  projectId: string;
  regions: RegionResponse[];
}) {
  const boundAction = createDatabaseAction.bind(null, organizationId, projectId);
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
        <Input
          id="name"
          name="name"
          required
          placeholder="my-database"
          pattern="[a-z][a-z0-9\-]{1,62}"
          minLength={2}
          maxLength={63}
          title="Start with a lowercase letter, then lowercase letters, numbers, or hyphens"
          className="w-48"
        />
        <p className="mt-1 text-xs text-slate-500">Lowercase, starts with a letter (e.g. my-database).</p>
      </div>
      <div>
        <Label htmlFor="region_code">Region</Label>
        <select
          id="region_code"
          name="region_code"
          required
          className="flex h-10 w-48 rounded-md border border-slate-700 bg-slate-900 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
        >
          {regions.map((region) => (
            <option key={region.id} value={region.code}>
              {region.name}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" disabled={pending || regions.length === 0}>
        {pending ? "Creating…" : "Create database"}
      </Button>
      {regions.length === 0 && (
        <p className="w-full text-sm text-slate-500">
          No regions are available yet — ask a platform admin to add one.
        </p>
      )}
    </form>
  );
}
