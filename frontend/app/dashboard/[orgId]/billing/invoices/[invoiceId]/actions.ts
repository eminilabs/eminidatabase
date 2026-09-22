"use server";

import { ApiError } from "@eminidatabase/sdk";
import { revalidatePath } from "next/cache";

import { getApiClient } from "@/lib/api-server";

type ActionState = { error?: string } | undefined;

function invoicePath(organizationId: string, invoiceId: string): string {
  return `/dashboard/${organizationId}/billing/invoices/${invoiceId}`;
}

export async function payManuallyAction(organizationId: string, invoiceId: string): Promise<ActionState> {
  const client = await getApiClient();
  try {
    await client.payInvoiceManually(organizationId, invoiceId);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(invoicePath(organizationId, invoiceId));
  return undefined;
}

export async function payWithCryptoAction(
  organizationId: string,
  invoiceId: string,
  _prevState: ActionState,
  formData: FormData
): Promise<ActionState> {
  const payCurrency = String(formData.get("pay_currency") ?? "") || undefined;
  const client = await getApiClient();
  try {
    await client.payInvoiceWithCrypto(organizationId, invoiceId, payCurrency);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(invoicePath(organizationId, invoiceId));
  return undefined;
}

export async function payWithMobileMoneyAction(
  organizationId: string,
  invoiceId: string,
  _prevState: ActionState,
  formData: FormData
): Promise<ActionState> {
  const mode = String(formData.get("mode") ?? "");
  const phoneNumber = String(formData.get("phone_number") ?? "");
  const client = await getApiClient();
  try {
    await client.payInvoiceWithMobileMoney(organizationId, invoiceId, mode, phoneNumber);
  } catch (err) {
    if (err instanceof ApiError) return { error: err.detail };
    return { error: "Something went wrong. Please try again." };
  }
  revalidatePath(invoicePath(organizationId, invoiceId));
  return undefined;
}
