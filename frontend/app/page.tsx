import { redirect } from "next/navigation";

import { getSessionToken } from "@/lib/session";

export default async function HomePage() {
  const token = await getSessionToken();
  redirect(token ? "/dashboard" : "/login");
}
