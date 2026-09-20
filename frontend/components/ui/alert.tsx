import { type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Alert({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800",
        className
      )}
      {...props}
    />
  );
}
