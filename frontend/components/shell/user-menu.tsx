"use client";

import { LogOut, User } from "lucide-react";
import { useState } from "react";

export function UserMenu({
  email,
  logoutAction,
}: {
  email: string;
  logoutAction: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full p-1 hover:bg-slate-800"
        aria-label="Account menu"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-800 text-slate-300">
          <User className="h-4 w-4" />
        </span>
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-2 w-56 rounded-md border border-slate-800 bg-slate-900 py-1 shadow-lg">
          <p className="truncate border-b border-slate-800 px-3 py-2 text-sm text-slate-500">{email}</p>
          <form action={logoutAction}>
            <button
              type="submit"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-800"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
