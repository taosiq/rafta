"use client";

import { Loader2, Sparkles } from "lucide-react";
import Link from "next/link";

import { useJobRunner } from "@/lib/hooks";

import { Button, EmptyState, ErrorNote } from "./ui";

/** Shown wherever there is no data yet: one click loads a realistic demo dataset. */
export function NoDataState({ what = "data" }: { what?: string }) {
  const { seed, busy, job, error } = useJobRunner();
  return (
    <div className="flex flex-col gap-4">
      <EmptyState
        title={`No ${what} yet`}
        action={
          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={seed} disabled={busy}>
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              {busy ? "Running pipeline…" : "Load demo dataset"}
            </Button>
            <Link href="/data" className="text-sm text-fg-2 underline-offset-4 hover:underline">
              or import your CSVs
            </Link>
          </div>
        }
      >
        Load a synthetic home-and-kitchen retailer (150 SKUs, two years of daily sales). Rafta then classifies,
        backtests six forecast models, sets reorder points and runs the policy simulation. It takes about a minute.
      </EmptyState>
      {job?.status === "failed" && <ErrorNote error={new Error(job.message ?? "Pipeline failed")} />}
      {error && <ErrorNote error={new Error(error)} />}
    </div>
  );
}
