"use client";

import { MoreVertical, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

import { deleteProjectAction } from "./actions";

export function ProjectCardMenu({
  organizationId,
  projectId,
  projectName,
}: {
  organizationId: string;
  projectId: string;
  projectName: string;
}) {
  const [open, setOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", handleClick);
    return () => window.removeEventListener("mousedown", handleClick);
  }, [open]);

  function handleConfirm() {
    startTransition(async () => {
      const result = await deleteProjectAction(organizationId, projectId);
      if (result?.error) {
        setError(result.error);
        setConfirmOpen(false);
      }
    });
  }

  return (
    <div className="relative shrink-0" ref={menuRef}>
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          setOpen((v) => !v);
        }}
        className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-slate-100"
        aria-label={`Actions for ${projectName}`}
      >
        <MoreVertical className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-44 rounded-md border border-slate-800 bg-slate-900 py-1 shadow-lg">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              setConfirmOpen(true);
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-400 hover:bg-slate-800"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete project
          </button>
        </div>
      )}

      {error && (
        <div className="absolute right-0 z-10 mt-1 w-64">
          <Alert>{error}</Alert>
        </div>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title={`Delete project "${projectName}"?`}
        description="This cannot be undone. All databases in this project must be deleted first."
        confirmLabel="Delete project"
        pending={pending}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
