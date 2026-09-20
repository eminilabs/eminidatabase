"use server";

import { ApiError, PlatformClient } from "@eminidatabase/sdk";
import { redirect } from "next/navigation";

import { setSessionToken } from "@/lib/session";

const BACKEND_API_URL = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000/api/v1";

export type LoginFormState = { error?: string; otpRequired?: boolean } | undefined;

export async function loginAction(
  _prevState: LoginFormState,
  formData: FormData
): Promise<LoginFormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const otpCode = formData.get("otp_code");

  const client = new PlatformClient(BACKEND_API_URL);
  try {
    await client.login(email, password, otpCode ? String(otpCode) : undefined);
  } catch (err) {
    if (err instanceof ApiError) {
      // The backend deliberately distinguishes these two 401s (cf.
      // backend/app/api/v1/endpoints/auth.py's `login`) — only the OTP one
      // should reveal the OTP field instead of just saying "wrong password".
      return { error: err.detail, otpRequired: err.detail === "Missing or invalid OTP code" };
    }
    return { error: "Something went wrong. Please try again." };
  }

  await setSessionToken(client.token!);
  redirect("/dashboard");
}
