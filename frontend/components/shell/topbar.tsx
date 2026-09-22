"use client";

import { NotificationsBell } from "@/components/notifications-bell";

import { Breadcrumb } from "./breadcrumb";
import { OrgSwitcher } from "./org-switcher";
import { UserMenu } from "./user-menu";

export function Topbar({
  email,
  logoutAction,
}: {
  email: string;
  logoutAction: () => Promise<void>;
}) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
      <Breadcrumb />
      <div className="flex items-center gap-2">
        <OrgSwitcher />
        <NotificationsBell />
        <UserMenu email={email} logoutAction={logoutAction} />
      </div>
    </header>
  );
}
