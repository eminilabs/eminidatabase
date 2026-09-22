"use client";

import { AlertTriangle } from "lucide-react";

import { logoutAction } from "@/app/actions/logout";
import { Button } from "@/components/ui/button";

export default function DashboardError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-4 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10 text-amber-400">
        <AlertTriangle className="h-6 w-6" />
      </span>
      <h1 className="text-lg font-semibold text-slate-100">Something went wrong</h1>
      <p className="max-w-sm text-sm text-slate-500">
        This can happen if your session expired. Try signing in again, or retry the page.
      </p>
      <div className="mt-2 flex gap-3">
        <Button variant="outline" onClick={() => reset()}>
          Try again
        </Button>
        <form action={logoutAction}>
          <Button type="submit">Sign in again</Button>
        </form>
      </div>
    </div>
  );
}
