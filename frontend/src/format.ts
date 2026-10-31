import type { MarketSummary } from "./api";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });

export const money = (n: number | null | undefined) => (n == null ? "—" : usd.format(n));

export const signedMoney = (n: number | null | undefined) =>
  n == null ? "—" : `${n > 0 ? "+" : n < 0 ? "−" : ""}${usd.format(Math.abs(n))}`;

/** $0.42 -> "42¢". Sub-cent prices keep one decimal. */
export const cents = (price: number | null | undefined) => {
  if (price == null || price <= 0) return "—";
  const c = price * 100;
  return `${Number.isInteger(Math.round(c * 10) / 10) ? Math.round(c) : c.toFixed(1)}¢`;
};

export const count = (n: number) => compact.format(n);

/** Market-implied chance of YES, 0–1. Uses the last trade, else the bid/ask midpoint. */
export function chance(m: Pick<MarketSummary, "last_price" | "yes_bid" | "yes_ask">): number | null {
  if (m.last_price && m.last_price > 0) return m.last_price;
  if (m.yes_bid && m.yes_ask) return (m.yes_bid + m.yes_ask) / 2;
  return m.yes_bid || m.yes_ask || null;
}

export const percent = (p: number | null) => (p == null ? "—" : `${Math.round(p * 100)}%`);

export function closesIn(iso: string | null): string {
  if (!iso) return "";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "Closed";
  const days = Math.floor(ms / 86_400_000);
  if (days > 365) return `Closes ${new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short" })}`;
  if (days >= 1) return `Closes in ${days} day${days === 1 ? "" : "s"}`;
  const hours = Math.max(1, Math.floor(ms / 3_600_000));
  return `Closes in ${hours} hour${hours === 1 ? "" : "s"}`;
}

/** "Today", "Tomorrow", or "Sunday, Nov 2" in the viewer's time zone. */
export function dayLabel(iso: string): string {
  const d = new Date(iso);
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (d.toDateString() === new Date().toDateString()) return "Today";
  if (d.toDateString() === tomorrow.toDateString()) return "Tomorrow";
  return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

export const clockTime = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

export const pnlClass =(n: number | null | undefined) =>
  n == null || Math.abs(n) < 0.005 ? "" : n > 0 ? "gain" : "loss";
