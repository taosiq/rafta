/** Formatting helpers. Pure functions, unit-tested in format.test.ts. */

const CURRENCY = process.env.NEXT_PUBLIC_CURRENCY ?? "USD";
const LOCALE = "en-US";

export function money(value: number | null | undefined, opts: { compact?: boolean } = {}): string {
  if (value == null || !Number.isFinite(value)) return "–";
  const compact = opts.compact ?? Math.abs(value) >= 100_000;
  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency: CURRENCY,
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : Math.abs(value) < 100 ? 2 : 0,
  }).format(value);
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return new Intl.NumberFormat(LOCALE, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}

export function compact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function pct(value: number | null | undefined, digits = 1, signed = false): string {
  if (value == null || !Number.isFinite(value)) return "–";
  const s = `${(value * 100).toFixed(digits)}%`;
  return signed && value > 0 ? `+${s}` : s.replace("-", "−");
}

export function signed(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "–";
  const s = num(Math.abs(value), digits);
  return value > 0 ? `+${s}` : value < 0 ? `−${s}` : s;
}

/** Dates from the API are ISO `YYYY-MM-DD`; format in UTC so server and client agree. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleDateString(LOCALE, { month: "short", day: "numeric", timeZone: "UTC" });
}

export function longDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return "–";
  return d.toLocaleDateString(LOCALE, { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
}

export function daysBetween(fromIso: string, toIso: string): number {
  const a = Date.parse(`${fromIso.slice(0, 10)}T00:00:00Z`);
  const b = Date.parse(`${toIso.slice(0, 10)}T00:00:00Z`);
  return Math.round((b - a) / 86_400_000);
}

export function relativeTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "–";
  const diff = (now - Date.parse(iso)) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86_400) return `${Math.floor(diff / 3600)} h ago`;
  return `${Math.floor(diff / 86_400)} d ago`;
}

/** "Nice" axis maximum: 1, 2, 2.5 or 5 x 10^n, at or above the value. */
export function niceCeil(value: number): number {
  if (value <= 0) return 1;
  const exp = Math.floor(Math.log10(value));
  const base = 10 ** exp;
  for (const m of [1, 2, 2.5, 5, 10]) if (m * base >= value) return m * base;
  return 10 * base;
}
