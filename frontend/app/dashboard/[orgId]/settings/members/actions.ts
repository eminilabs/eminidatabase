"use server";

import { ApiError } from "@eminidatabase/sdk";
import type { MembershipRole } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

export type MemberFormState = { error?: string } | undefined;

export async function addMemberAction(
  organizationId: string,
  _prevState: MemberFormState,
  formData: FormData
): Promise<MemberFormState> {
  const email = String(formData.get("email") ?? "");
  const role = String(formData.get("role") ?? "developer") as MembershipRole;
  const client = await getApiClient();
  try {
    await client.addMember(organizationId, email, role);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(`/dashboard/${organizationId}/settings/members`);
  return undefined;
}

export async function removeMemberAction(
  organizationId: string,
  targetUserId: string
): Promise<{ error?: string } | void> {
  const client = await getApiClient();
  try {
    await client.removeMember(organizationId, targetUserId);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(`/dashboard/${organizationId}/settings/members`);
}
