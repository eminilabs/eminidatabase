import type { PlanResponse } from "@eminidatabase/sdk";
import { Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import { SelectPlanButton } from "./select-plan-button";

function formatMoney(value: unknown): string {
  const n = Number(value ?? 0);
  return n === 0 ? "$0" : `$${n.toFixed(2)}`;
}

function quotaLines(quotas: Record<string, unknown>): string[] {
  const lines: string[] = [];
  if (typeof quotas.max_databases === "number") {
    lines.push(`${quotas.max_databases} database${quotas.max_databases === 1 ? "" : "s"}`);
  }
  if (typeof quotas.max_storage_gb === "number") {
    lines.push(`${quotas.max_storage_gb} GB storage`);
  }
  if (typeof quotas.max_cpu_total === "number") {
    lines.push(`${quotas.max_cpu_total} vCPU total`);
  }
  return lines;
}

export function PricingCards({
  organizationId,
  plans,
  currentPlanId,
}: {
  organizationId: string;
  plans: PlanResponse[];
  currentPlanId: string;
}) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      {plans.map((plan) => {
        const quotas = (plan.quotas ?? {}) as Record<string, unknown>;
        const pricing = (plan.pricing ?? {}) as Record<string, unknown>;
        const isPro = plan.name !== "free";
        const isCurrent = plan.id === currentPlanId;
        const rates = [
          pricing.cpu_hours ? `$${pricing.cpu_hours} / CPU-hour` : null,
          pricing.storage_gb_hours ? `$${pricing.storage_gb_hours} / GB-hour storage` : null,
        ].filter((r): r is string => r !== null);

        return (
          <Card
            key={plan.id}
            className={cn("flex flex-col", isPro && "border-emerald-600/50 ring-1 ring-emerald-600/20")}
          >
            <CardContent className="flex flex-1 flex-col gap-5 py-6">
              <div>
                {isPro && (
                  <Badge variant="default" className="mb-2">
                    Most popular
                  </Badge>
                )}
                <h3 className="text-lg font-semibold capitalize text-slate-100">{plan.name}</h3>
                <p className="mt-1">
                  <span className="text-2xl font-semibold text-slate-100">{formatMoney(pricing.base_fee)}</span>
                  <span className="text-sm text-slate-500"> /month{rates.length > 0 ? " + usage" : ""}</span>
                </p>
              </div>

              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600">
                  What&apos;s included
                </p>
                <ul className="space-y-2 text-sm text-slate-300">
                  {quotaLines(quotas).map((line) => (
                    <li key={line} className="flex items-center gap-2">
                      <Check className="h-4 w-4 shrink-0 text-emerald-500" />
                      {line}
                    </li>
                  ))}
                </ul>
              </div>

              {rates.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600">
                    Usage-based rates
                  </p>
                  <ul className="space-y-1 text-sm text-slate-400">
                    {rates.map((rate) => (
                      <li key={rate}>{rate}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="mt-auto pt-2">
                <SelectPlanButton
                  organizationId={organizationId}
                  planId={plan.id}
                  current={isCurrent}
                  label={isPro ? "Select plan" : "Downgrade to Free"}
                />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
