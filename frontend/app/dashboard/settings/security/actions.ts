"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { getApiClient } from "@/lib/api-server";
import { clearSessionToken } from "@/lib/session";

export async function enableMfaAction(): Promise<{ provisioningUri?: string; error?: string }> {
  const client = await getApiClient();
  try {
    const res = await client.enableMfa();
    return { provisioningUri: res.provisioning_uri };
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
}

export async function verifyMfaAction(
  otpCode: string
): Promise<{ error?: string; success?: boolean }> {
  const client = await getApiClient();
  try {
    await client.verifyMfa(otpCode);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath("/dashboard/settings/security");
  return { success: true };
}

export async function revokeAllSessionsAction(): Promise<void> {
  const client = await getApiClient();
  await client.revokeAllSessions();
  // The cookie's own JWT is now invalid too (revoke-all bumps token_version
  // for every session, including this one) — clear it and send the user
  // back to /login rather than leaving a dead cookie around.
  await clearSessionToken();
  redirect("/login");
}
