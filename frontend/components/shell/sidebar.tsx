"use client";

import {
  Archive,
  ArrowLeft,
  Database as DatabaseIcon,
  CreditCard,
  FolderKanban,
  Key,
  LayoutGrid,
  Plug,
  ShieldCheck,
  Table2,
  Terminal,
  Users,
  Webhook,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { NavItem } from "./nav-item";

const DB_MATCH = /^\/dashboard\/([^/]+)\/projects\/([^/]+)\/databases\/([^/]+)/;

export function Sidebar() {
  const pathname = usePathname();

  const dbMatch = pathname.match(DB_MATCH);
  const isReservedTop =
    pathname.startsWith("/dashboard/organizations") || pathname.startsWith("/dashboard/settings");
  const orgId = !isReservedTop ? pathname.split("/")[2] : undefined;

  if (dbMatch) {
    const [, oid, pid, did] = dbMatch;
    const base = `/dashboard/${oid}/projects/${pid}/databases/${did}`;
    return (
      <aside className="flex h-full w-64 shrink-0 flex-col overflow-y-auto border-r border-slate-800 bg-slate-950">
        <SidebarLogo />
        <div className="border-b border-slate-800 p-4">
          <Link
            href={`/dashboard/${oid}/projects/${pid}/databases`}
            className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-100"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to databases
          </Link>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          <NavItem href={base} icon={LayoutGrid} label="Overview" active={pathname === base} />
          <p className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-slate-600">
            Postgres database
          </p>
          <NavItem
            href={`${base}/tables`}
            icon={Table2}
            label="Tables"
            active={pathname.startsWith(`${base}/tables`)}
          />
          <NavItem
            href={`${base}/sql`}
            icon={Terminal}
            label="SQL Editor"
            active={pathname.startsWith(`${base}/sql`)}
          />
          <NavItem
            href={`${base}/backups`}
            icon={Archive}
            label="Backup & Restore"
            active={pathname.startsWith(`${base}/backups`)}
          />
          <NavItem
            href={`${base}/roles`}
            icon={Users}
            label="Roles"
            active={pathname.startsWith(`${base}/roles`)}
          />
          <NavItem
            href={`${base}/extensions`}
            icon={Plug}
            label="Extensions"
            active={pathname.startsWith(`${base}/extensions`)}
          />
        </nav>
      </aside>
    );
  }

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col overflow-y-auto border-r border-slate-800 bg-slate-950">
      <SidebarLogo />

      {orgId && (
        <nav className="flex-1 space-y-1 p-3">
          <p className="px-3 pb-1 pt-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
            Organization
          </p>
          <NavItem
            href={`/dashboard/${orgId}/projects`}
            icon={FolderKanban}
            label="Projects"
            active={pathname.startsWith(`/dashboard/${orgId}/projects`)}
          />
          <NavItem
            href={`/dashboard/${orgId}/databases`}
            icon={DatabaseIcon}
            label="Databases"
            active={pathname.startsWith(`/dashboard/${orgId}/databases`)}
          />
          <NavItem
            href={`/dashboard/${orgId}/billing`}
            icon={CreditCard}
            label="Billing"
            active={pathname.startsWith(`/dashboard/${orgId}/billing`)}
          />
          <p className="px-3 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-slate-600">
            Settings
          </p>
          <NavItem
            href={`/dashboard/${orgId}/settings/members`}
            icon={Users}
            label="Members"
            active={pathname.startsWith(`/dashboard/${orgId}/settings/members`)}
          />
          <NavItem
            href={`/dashboard/${orgId}/settings/api-keys`}
            icon={Key}
            label="API keys"
            active={pathname.startsWith(`/dashboard/${orgId}/settings/api-keys`)}
          />
          <NavItem
            href={`/dashboard/${orgId}/settings/webhooks`}
            icon={Webhook}
            label="Webhooks"
            active={pathname.startsWith(`/dashboard/${orgId}/settings/webhooks`)}
          />
        </nav>
      )}

      <div className="border-t border-slate-800 p-3">
        <NavItem
          href="/dashboard/settings/security"
          icon={ShieldCheck}
          label="Account security"
          active={pathname.startsWith("/dashboard/settings/security")}
        />
      </div>
    </aside>
  );
}

function SidebarLogo() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2 border-b border-slate-800 px-4 py-4">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-emerald-600 text-white">
        <DatabaseIcon className="h-4 w-4" />
      </span>
      <span className="text-sm font-semibold text-slate-100">eminidatabase</span>
    </Link>
  );
}
