"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";

import { changePlanAction } from "./actions";

export function SelectPlanButton({
  organizationId,
  planId,
  current,
  label,
}: {
  organizationId: string;
  planId: string;
  current: boolean;
  label: string;
}) {
  const boundAction = changePlanAction.bind(null, organizationId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  return (
    <form action={action}>
      <input type="hidden" name="plan_id" value={planId} />
      <Button type="submit" disabled={pending || current} variant={current ? "outline" : "default"} className="w-full">
        {current ? "Current plan" : pending ? "Updating…" : label}
      </Button>
      {state?.error && <p className="mt-2 text-xs text-red-400">{state.error}</p>}
    </form>
  );
}
