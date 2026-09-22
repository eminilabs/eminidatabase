import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export type BadgeVariant = "default" | "success" | "warning" | "danger" | "neutral";

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-indigo-500/10 text-indigo-300 ring-1 ring-inset ring-indigo-500/30",
  success: "bg-emerald-500/10 text-emerald-300 ring-1 ring-inset ring-emerald-500/30",
  warning: "bg-amber-500/10 text-amber-300 ring-1 ring-inset ring-amber-500/30",
  danger: "bg-red-500/10 text-red-300 ring-1 ring-inset ring-red-500/30",
  neutral: "bg-slate-500/10 text-slate-300 ring-1 ring-inset ring-slate-500/20",
};

export function Badge({
  variant = "neutral",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) {
  return (
    <span
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
      {...props}
    />
  );
}

const SUCCESS_STATUSES = new Set([
  "running",
  "active",
  "paid",
  "succeeded",
  "completed",
  "enabled",
]);
const WARNING_STATUSES = new Set([
  "creating",
  "pending",
  "provisioning",
  "finalized",
  "in_progress",
  "restoring",
  "updating",
  "suspending",
  "suspended",
  "migrating",
]);
const DANGER_STATUSES = new Set([
  "failed",
  "deleted",
  "error",
  "void",
  "cancelled",
  "revoked",
  "failing",
  "deleting",
]);

export function statusBadgeVariant(status: string): BadgeVariant {
  const normalized = status.toLowerCase();
  if (SUCCESS_STATUSES.has(normalized)) return "success";
  if (WARNING_STATUSES.has(normalized)) return "warning";
  if (DANGER_STATUSES.has(normalized)) return "danger";
  return "neutral";
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge variant={statusBadgeVariant(status)} className={className}>
      {status}
    </Badge>
  );
}
