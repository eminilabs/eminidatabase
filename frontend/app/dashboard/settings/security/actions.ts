"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

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
