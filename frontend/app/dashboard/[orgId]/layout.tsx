import Link from "next/link";

const TABS = [
  { href: "/projects", label: "Projects" },
  { href: "/billing", label: "Billing" },
  { href: "/settings/members", label: "Settings" },
];

export default async function OrgLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const base = `/dashboard/${orgId}`;

  return (
    <div className="space-y-6">
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
