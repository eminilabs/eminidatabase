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
    // The proxy's local exp-only check passed, but the backend rejects the
    // token anyway (revoked via /auth/sessions/revoke-all, most commonly) —
    // the backend is the authoritative check, this is where that gets
    // enforced. Redirect through a route handler that clears the cookie
    // first (a Server Component can't do that itself) — otherwise proxy.ts
    // still sees a not-yet-expired cookie on the very next request and
    // bounces straight back here, looping against /login forever.
    redirect("/api/auth/invalidate-session");
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
