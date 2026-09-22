"use client";

import { type LucideIcon } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

export function NavItem({
  href,
  icon: Icon,
  label,
  active,
}: {
  href: string;
  icon: LucideIcon;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        active ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-100"
      )}
    >
      <Icon className={cn("h-4 w-4 shrink-0", active ? "text-emerald-400" : "text-slate-500")} />
      {label}
    </Link>
  );
}
