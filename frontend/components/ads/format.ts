// Shared formatting for the operator Ads & CRM surface. Money crosses the API as integer CENTS
// (ADR-0003 keeps every figure in pure backend code) — the UI only DISPLAYS, never computes spend.

/** Integer cents → "$1,234" (no decimals — these are budgets/spend, dollar-precision reads cleaner). */
export const fromCents = (cents: number) =>
  (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });

/** Integer cents → "$12.34" for small per-lead / per-day figures. */
export const fromCents2 = (cents: number) =>
  (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });

/** Whole counts with thousands separators (impressions, clicks). */
export const count = (n: number) => n.toLocaleString("en-US");

/** A short, human "3 days ago" / "in 2 hours" from an ISO timestamp. */
export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const past = diffMs >= 0;
  const s = Math.abs(diffMs) / 1000;
  const units: [number, string][] = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [7, "day"],
    [4.34524, "week"],
    [12, "month"],
    [Number.POSITIVE_INFINITY, "year"],
  ];
  let value = s;
  let unit = "second";
  for (const [factor, name] of units) {
    if (value < factor) {
      unit = name;
      break;
    }
    value /= factor;
  }
  const rounded = Math.max(1, Math.floor(value));
  const plural = rounded === 1 ? "" : "s";
  return past ? `${rounded} ${unit}${plural} ago` : `in ${rounded} ${unit}${plural}`;
}
