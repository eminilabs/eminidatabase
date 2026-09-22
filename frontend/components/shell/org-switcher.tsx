"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2, ChevronDown } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import type { OrganizationResponse } from "@eminidatabase/sdk";
import { cn } from "@/lib/utils";

function useOrganizations() {
  return useQuery({
    queryKey: ["organizations"],
    queryFn: async (): Promise<OrganizationResponse[]> => {
      const res = await fetch("/api/organizations");
      if (!res.ok) throw new Error("Failed to load organizations");
      return res.json();
    },
    // No staleTime: a newly created organization must show up here right
    // after the create-organization redirect, on the very next mount — a
    // cached-as-fresh empty list (captured before any org existed, e.g. on
    // /dashboard/organizations/new) would otherwise stick around and hide it.
  });
}

export function OrgSwitcher() {
  const pathname = usePathname();
  const { data: organizations = [], refetch } = useOrganizations();
  const [open, setOpen] = useState(false);

  // This component lives in the persistent dashboard layout, so it never
  // remounts on a client-side navigation (e.g. right after creating an
  // organization and being redirected to its /projects page) — TanStack
  // Query's "refetch on mount" never fires there. Refetching on every
  // pathname change instead catches that transition explicitly.
  useEffect(() => {
    refetch();
  }, [pathname, refetch]);

  const isReservedTop =
    pathname.startsWith("/dashboard/organizations") || pathname.startsWith("/dashboard/settings");
  const orgId = !isReservedTop ? pathname.split("/")[2] : undefined;
  const currentOrg = organizations.find((org) => org.id === orgId);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={isReservedTop}
        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-slate-800 disabled:cursor-default disabled:hover:bg-transparent"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-emerald-600 text-white">
          <Building2 className="h-3.5 w-3.5" />
        </span>
        <span className="max-w-[10rem] truncate font-medium text-slate-100">
          {currentOrg?.name ?? "eminidatabase"}
        </span>
        {!isReservedTop && <ChevronDown className="h-4 w-4 text-slate-500" />}
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-56 rounded-md border border-slate-800 bg-slate-900 py-1 shadow-lg">
          {organizations.map((org) => (
            <Link
              key={org.id}
              href={`/dashboard/${org.id}/projects`}
              onClick={() => setOpen(false)}
              className={cn(
                "block truncate px-3 py-2 text-sm hover:bg-slate-800",
                org.id === orgId ? "font-medium text-slate-100" : "text-slate-400"
              )}
            >
              {org.name}
            </Link>
          ))}
          <Link
            href="/dashboard/organizations/new"
            onClick={() => setOpen(false)}
            className="block border-t border-slate-800 px-3 py-2 text-sm text-slate-500 hover:bg-slate-800 hover:text-slate-100"
          >
            + New organization
          </Link>
        </div>
      )}
    </div>
  );
}
