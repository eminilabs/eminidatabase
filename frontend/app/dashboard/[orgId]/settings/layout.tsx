import Link from "next/link";

const TABS = [
  { href: "/members", label: "Members" },
  { href: "/api-keys", label: "API keys" },
  { href: "/webhooks", label: "Webhooks" },
];

export default async function SettingsLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  const base = `/dashboard/${orgId}/settings`;

  return (
    <div className="space-y-4">
      <nav className="flex gap-4 text-sm">
        {TABS.map((tab) => (
          <Link key={tab.href} href={`${base}${tab.href}`} className="text-slate-600 hover:text-slate-900 hover:underline">
            {tab.label}
          </Link>
        ))}
      </nav>
      {children}
    </div>
  );
}
