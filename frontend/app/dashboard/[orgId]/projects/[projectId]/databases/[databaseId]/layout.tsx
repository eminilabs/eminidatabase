import Link from "next/link";

import { getApiClient } from "@/lib/api-server";

const TABS = [
  { href: "", label: "Overview" },
  { href: "/sql", label: "SQL Editor" },
  { href: "/backups", label: "Backups" },
];

export default async function DatabaseDetailLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string; projectId: string; databaseId: string }>;
}) {
  const { orgId, projectId, databaseId } = await params;
  const client = await getApiClient();
  const database = await client.getDatabase(orgId, projectId, databaseId);

  const base = `/dashboard/${orgId}/projects/${projectId}/databases/${databaseId}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{database.name}</h1>
        <p className="text-sm text-slate-500">{database.status}</p>
      </div>
      <nav className="flex gap-1 border-b border-slate-200">
        {TABS.map((tab) => (
          <Link
            key={tab.href}
            href={`${base}${tab.href}`}
            className="rounded-t-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            {tab.label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
