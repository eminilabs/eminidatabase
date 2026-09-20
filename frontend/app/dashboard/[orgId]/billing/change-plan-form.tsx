"use client";

import { useActionState } from "react";

import type { PlanResponse } from "@eminidatabase/sdk";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { changePlanAction } from "./actions";

export function ChangePlanForm({
  organizationId,
  plans,
  currentPlanId,
}: {
  organizationId: string;
  plans: PlanResponse[];
  currentPlanId: string;
}) {
  const boundAction = changePlanAction.bind(null, organizationId);
  const [state, action, pending] = useActionState(boundAction, undefined);

  return (
    <form action={action} className="flex flex-wrap items-end gap-3">
      {state?.error && (
        <div className="w-full">
          <Alert>{state.error}</Alert>
          {state.error.toLowerCase().includes("mfa") && (
            <p className="mt-1 text-xs text-slate-500">
              Enable two-factor authentication under Security, then try again.
            </p>
          )}
        </div>
      )}
      <select
        name="plan_id"
        defaultValue={currentPlanId}
        className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm"
      >
        {plans.map((plan) => (
          <option key={plan.id} value={plan.id}>
            {plan.name}
          </option>
        ))}
      </select>
      <Button type="submit" variant="outline" disabled={pending}>
        {pending ? "Changing…" : "Change plan"}
      </Button>
    </form>
  );
}
