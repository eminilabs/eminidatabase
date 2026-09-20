"use server";

import { redirect } from "next/navigation";

import { clearSessionToken } from "@/lib/session";

export async function logoutAction() {
  await clearSessionToken();
  redirect("/login");
}
