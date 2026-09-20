import { NextResponse } from "next/server";

import { apiErrorResponse } from "@/lib/api-error-response";
import { getApiClient } from "@/lib/api-server";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ orgId: string; invoiceId: string }> }
) {
  const { orgId, invoiceId } = await params;
  const client = await getApiClient();
  try {
    const invoice = await client.getInvoice(orgId, invoiceId);
    return NextResponse.json(invoice);
  } catch (err) {
    return apiErrorResponse(err);
  }
}
