import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Alert({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-md border border-red-900 bg-red-950/40 px-3 py-2 text-sm text-red-300",
        className
      )}
      {...props}
    />
  );
}
