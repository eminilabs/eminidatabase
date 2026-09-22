"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

type ActionState = { error?: string } | undefined;

function dbBasePath(organizationId: string, projectId: string, databaseId: string): string {
  return `/dashboard/${organizationId}/projects/${projectId}/databases/${databaseId}`;
}

export async function installExtensionAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  _prevState: ActionState,
  formData: FormData
): Promise<ActionState> {
  const name = String(formData.get("name") ?? "");
  const client = await getApiClient();
  try {
    await client.installExtension(organizationId, projectId, databaseId, name);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(dbBasePath(organizationId, projectId, databaseId));
  return undefined;
}

export async function dropExtensionAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  name: string
): Promise<void> {
  const client = await getApiClient();
  await client.dropExtension(organizationId, projectId, databaseId, name);
  revalidatePath(dbBasePath(organizationId, projectId, databaseId));
}

export type RoleFormState = { error?: string; created?: { roleName: string; password: string } } | undefined;

export async function createRoleAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  _prevState: RoleFormState,
  formData: FormData
): Promise<RoleFormState> {
  const name = String(formData.get("name") ?? "");
  const scope = String(formData.get("scope") ?? "app") as "app" | "readonly";
  const client = await getApiClient();
  try {
    const created = await client.createRole(organizationId, projectId, databaseId, name, scope);
    revalidatePath(dbBasePath(organizationId, projectId, databaseId));
    return { created: { roleName: created.role_name, password: created.password } };
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
}

export async function deleteRoleAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  credentialId: string
): Promise<void> {
  const client = await getApiClient();
  await client.deleteRole(organizationId, projectId, databaseId, credentialId);
  revalidatePath(dbBasePath(organizationId, projectId, databaseId));
}

export async function rotateRoleAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  credentialId: string
): Promise<{ roleName: string; password: string }> {
  const client = await getApiClient();
  const rotated = await client.rotateRole(organizationId, projectId, databaseId, credentialId);
  revalidatePath(dbBasePath(organizationId, projectId, databaseId));
  return { roleName: rotated.role_name, password: rotated.password };
}

export async function suspendDatabaseAction(
  organizationId: string,
  projectId: string,
  databaseId: string
): Promise<ActionState> {
  const client = await getApiClient();
  try {
    await client.suspendDatabase(organizationId, projectId, databaseId);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(dbBasePath(organizationId, projectId, databaseId));
  return undefined;
}

export async function resumeDatabaseAction(
  organizationId: string,
  projectId: string,
  databaseId: string
): Promise<ActionState> {
  const client = await getApiClient();
  try {
    await client.resumeDatabase(organizationId, projectId, databaseId);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(dbBasePath(organizationId, projectId, databaseId));
  return undefined;
}

export type ResizeFormState = { error?: string } | undefined;

export async function resizeDatabaseAction(
  organizationId: string,
  projectId: string,
  databaseId: string,
  _prevState: ResizeFormState,
  formData: FormData
): Promise<ResizeFormState> {
  const client = await getApiClient();
  try {
    await client.resizeDatabase(organizationId, projectId, databaseId, {
      cpu_limit: Number(formData.get("cpu_limit")),
      ram_limit_mb: Number(formData.get("ram_limit_mb")),
      storage_limit_gb: Number(formData.get("storage_limit_gb")),
    });
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(dbBasePath(organizationId, projectId, databaseId));
  return undefined;
}
