"use server";

import { ApiError, PlatformClient } from "@eminidatabase/sdk";
import { redirect } from "next/navigation";

import { setSessionToken } from "@/lib/session";

const BACKEND_API_URL = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000/api/v1";

export type AuthFormState = { error?: string } | undefined;

export async function registerAction(
  _prevState: AuthFormState,
  formData: FormData
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  const client = new PlatformClient(BACKEND_API_URL);
  try {
    await client.register(email, password);
    await client.login(email, password);
  } catch (err) {
    if (err instanceof ApiError) {
      return { error: err.detail };
    }
    return { error: "Something went wrong. Please try again." };
  }

  await setSessionToken(client.token!);
  redirect("/dashboard");
}
