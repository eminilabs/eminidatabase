"use server";

import { ApiError } from "@eminidatabase/sdk";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

type ActionState = { error?: string } | undefined;

function backupsPath(organizationId: string, projectId: string, databaseId: string): string {
  return `/dashboard/${organizationId}/projects/${projectId}/databases/${databaseId}/backups`;
}

export async function createBackupAction(
  organizationId: string,
  projectId: string,
  databaseId: string
): Promise<void> {
  const client = await getApiClient();
  await client.createBackup(organizationId, projectId, databaseId);
  revalidatePath(backupsPath(organizationId, projectId, databaseId));
}

export async function restoreBackupAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  backupId: string,
  _prevState: ActionState,
  formData: FormData
): Promise<ActionState> {
  const name = String(formData.get("name") ?? "");
  const client = await getApiClient();
  try {
    await client.restoreBackup(organizationId, projectId, databaseId, backupId, name);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  // The restored database is a new, separate database — its own provisioning
  // status is already visible via the existing polling database list.
  redirect(`/dashboard/${organizationId}/projects/${projectId}/databases`);
}

export type PolicyFormState = { error?: string; success?: boolean } | undefined;

export async function setBackupPolicyAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  _prevState: PolicyFormState,
  formData: FormData
): Promise<PolicyFormState> {
  const enabled = formData.get("enabled") === "on";
  const frequencyHours = Number(formData.get("frequency_hours"));
  const retentionDays = Number(formData.get("retention_days"));
  const client = await getApiClient();
  try {
    await client.setBackupPolicy(organizationId, projectId, databaseId, {
      enabled,
      frequency_hours: frequencyHours,
      retention_days: retentionDays,
    });
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(backupsPath(organizationId, projectId, databaseId));
  return { success: true };
}
