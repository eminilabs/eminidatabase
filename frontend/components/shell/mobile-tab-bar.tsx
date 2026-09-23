"use client";

import { CreditCard, Database as DatabaseIcon, FolderKanban, Settings, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

export function MobileTabBar() {
  const pathname = usePathname();

  const isReservedTop =
    pathname.startsWith("/dashboard/organizations") || pathname.startsWith("/dashboard/settings");
  const orgId = !isReservedTop ? pathname.split("/")[2] : undefined;

  if (!orgId) return null;

  const tabs = [
    {
      href: `/dashboard/${orgId}/projects`,
      icon: FolderKanban,
      label: "Projects",
      active: pathname.startsWith(`/dashboard/${orgId}/projects`),
    },
    {
      href: `/dashboard/${orgId}/databases`,
      icon: DatabaseIcon,
      label: "Databases",
      active: pathname.startsWith(`/dashboard/${orgId}/databases`),
    },
    {
      href: `/dashboard/${orgId}/billing`,
      icon: CreditCard,
      label: "Billing",
      active: pathname.startsWith(`/dashboard/${orgId}/billing`),
    },
    {
      href: `/dashboard/${orgId}/settings/members`,
      icon: Settings,
      label: "Settings",
      active: pathname.startsWith(`/dashboard/${orgId}/settings`),
    },
    {
      href: "/dashboard/settings/security",
      icon: ShieldCheck,
      label: "Security",
      active: pathname.startsWith("/dashboard/settings/security"),
    },
  ];

  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-slate-800 bg-slate-950 md:hidden">
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={cn(
            "flex flex-1 flex-col items-center gap-1 py-2.5 text-xs font-medium",
            tab.active ? "text-emerald-400" : "text-slate-500"
          )}
        >
          <tab.icon className="h-5 w-5" />
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
