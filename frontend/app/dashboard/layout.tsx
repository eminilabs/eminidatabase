import Link from "next/link";
import { redirect } from "next/navigation";

import { logoutAction } from "@/app/actions/logout";
import { NotificationsBell } from "@/components/notifications-bell";
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
    <div className="flex min-h-screen">
      <aside className="flex w-64 flex-col border-r border-slate-200 bg-white p-4">
        <Link href="/dashboard" className="mb-6 text-lg font-semibold text-slate-900">
          eminidatabase
        </Link>
        <nav className="flex-1 space-y-1 text-sm text-slate-600">
          <Link href="/dashboard/settings/security" className="block rounded-md px-3 py-2 hover:bg-slate-100">
            Security
          </Link>
        </nav>
        <div className="border-t border-slate-100 pt-4">
          <p className="truncate text-sm text-slate-500">{email}</p>
          <form action={logoutAction}>
            <button
              type="submit"
              className="mt-2 text-sm text-slate-500 underline hover:text-slate-900"
            >
              Sign out
            </button>
          </form>
        </div>
      </aside>
      <div className="flex-1">
        <header className="flex items-center justify-end border-b border-slate-200 bg-white px-6 py-3">
          <NotificationsBell />
        </header>
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
