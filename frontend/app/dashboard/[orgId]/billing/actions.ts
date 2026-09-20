"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

export type PlanFormState = { error?: string } | undefined;

export async function changePlanAction(
  organizationId: string,
  _prevState: PlanFormState,
  formData: FormData
): Promise<PlanFormState> {
  const planId = String(formData.get("plan_id") ?? "");
  const client = await getApiClient();
  try {
    await client.updateSubscription(organizationId, planId);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(`/dashboard/${organizationId}/billing`);
  return undefined;
}
