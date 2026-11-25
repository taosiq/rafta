import type { Abc, Status } from "./api";

/** Fixed class colours: used identically in badges, the matrix and every chart. */
export const CLASS_COLOR: Record<Abc, string> = {
  A: "var(--class-a)",
  B: "var(--class-b)",
  C: "var(--class-c)",
};

export const CLASS_LABEL: Record<Abc, string> = {
  A: "High value",
  B: "Medium value",
  C: "Low value",
};

export const XYZ_LABEL = { X: "Stable", Y: "Variable", Z: "Erratic" } as const;

export const STATUS_META: Record<Status, { label: string; short: string; color: string; soft: string; ink: string }> = {
  stockout_risk: {
    label: "Stock-out risk",
    short: "Risk",
    color: "var(--risk)",
    soft: "var(--risk-soft)",
    ink: "var(--risk-ink)",
  },
  reorder: {
    label: "Reorder soon",
    short: "Reorder",
    color: "var(--reorder)",
    soft: "var(--reorder-soft)",
    ink: "var(--reorder-ink)",
  },
  healthy: {
    label: "Healthy",
    short: "Healthy",
    color: "var(--healthy)",
    soft: "var(--healthy-soft)",
    ink: "var(--healthy-ink)",
  },
};

/** Policies are their own validated categorical set, in fixed order. */
export const POLICY_COLORS = ["var(--policy-1)", "var(--policy-2)", "var(--policy-3)"];
export const policyColor = (i: number) => POLICY_COLORS[i] ?? "var(--reference)";

export const MODEL_LABEL: Record<string, string> = {
  seasonal_naive: "Seasonal naive",
  moving_average: "Moving average",
  ses: "Exp. smoothing",
  holt_winters: "Holt-Winters",
  croston: "Croston (SBA)",
  lightgbm: "LightGBM",
};
