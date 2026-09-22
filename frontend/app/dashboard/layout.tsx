import { redirect } from "next/navigation";

import { logoutAction } from "@/app/actions/logout";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { getApiClient } from "@/lib/api-server";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const client = await getApiClient();
  let email: string;
  try {
    email = (await client.me()).email;
  } catch {
    // The proxy's cookie-presence check passed, but the token itself is
    // invalid/expired against the backend — the backend is the authoritative
    // check, this is where that gets enforced.
    redirect("/login");
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar email={email} logoutAction={logoutAction} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
