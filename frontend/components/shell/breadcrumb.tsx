"use client";

import { usePathname } from "next/navigation";

const LABELS: Record<string, string> = {
  projects: "Projects",
  billing: "Billing",
  settings: "Settings",
  members: "Members",
  "api-keys": "API keys",
  webhooks: "Webhooks",
  deliveries: "Deliveries",
  sql: "SQL Editor",
  backups: "Backup & Restore",
  tables: "Tables",
  roles: "Roles",
  extensions: "Extensions",
  security: "Account security",
  databases: "Databases",
  organizations: "Organizations",
  new: "New",
  invoices: "Invoices",
};

function isIdentifier(segment: string) {
  return /^[0-9a-f-]{8,}$/i.test(segment) || /^\d+$/.test(segment);
}

export function Breadcrumb() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean).slice(1);
  const crumbs = segments.filter((segment) => !isIdentifier(segment)).map((segment) => LABELS[segment] ?? segment);

  if (crumbs.length === 0) {
    return <span className="text-sm font-medium text-slate-100">Dashboard</span>;
  }

  return (
    <nav className="flex items-center gap-1.5 text-sm">
      {crumbs.map((crumb, index) => (
        <span key={`${crumb}-${index}`} className="flex items-center gap-1.5">
          {index > 0 && <span className="text-slate-700">/</span>}
          <span className={index === crumbs.length - 1 ? "font-medium text-slate-100" : "text-slate-500"}>
            {crumb}
          </span>
        </span>
      ))}
    </nav>
  );
}
