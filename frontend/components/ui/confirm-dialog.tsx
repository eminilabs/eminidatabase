"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect } from "react";

import { Button } from "./button";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  destructive = true,
  pending = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  destructive?: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="w-full max-w-sm rounded-lg border border-slate-800 bg-slate-900 shadow-xl"
      >
        <div className="flex items-start gap-3 p-5">
          {destructive && (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-red-500/10 text-red-400">
              <AlertTriangle className="h-5 w-5" />
            </span>
          )}
          <div className="min-w-0">
            <h2 id="confirm-dialog-title" className="text-base font-semibold text-slate-100">
              {title}
            </h2>
            <p className="mt-1 text-sm text-slate-400">{description}</p>
          </div>
        </div>
        <div className="flex justify-end gap-3 border-t border-slate-800 px-5 py-4">
          <Button variant="outline" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <Button
            onClick={onConfirm}
            disabled={pending}
            className={destructive ? "bg-red-600 text-white hover:bg-red-500" : undefined}
          >
            {pending ? "Please wait…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
