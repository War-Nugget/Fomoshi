// Typed wrapper around the Fomoshi API.

export type Side = "yes" | "no";
export type Action = "buy" | "sell";

export interface User {
  id: number;
  username: string;
  cash: number;
}

export interface MarketSummary {
  ticker: string;
  event_ticker: string;
  label: string;
  status: string;
  yes_bid: number | null;
  yes_ask: number | null;
  no_bid: number | null;
  no_ask: number | null;
  last_price: number | null;
  volume: number;
  volume_24h: number;
  open_interest: number;
  close_time: string | null;
  result: string;
}

export interface EventSummary {
  event_ticker: string;
  series_ticker: string;
  title: string;
  sub_title: string;
  category: string;
  markets: MarketSummary[];
}

export interface MarketDetail extends MarketSummary {
  event_title: string;
  rules_primary: string;
}

export interface BookLevel {
  price: number;
  quantity: number;
}

export interface OrderBook {
  ticker: string;
  yes_bids: BookLevel[];
  yes_asks: BookLevel[];
  no_bids: BookLevel[];
  no_asks: BookLevel[];
}

export interface TradeRequest {
  ticker: string;
  side: Side;
  action: Action;
  quantity: number;
  limit_price?: number;
}

export interface Preview {
  filled_quantity: number;
  unfilled_quantity: number;
  avg_price: number | null;
  total: number;
  fills: BookLevel[];
  max_payout: number;
}

export interface Trade {
  id: number;
  ticker: string;
  side: Side;
  action: Action | "settle";
  quantity: number;
  avg_price: number;
  total: number;
  realized_pnl: number;
  created_at: string;
}

export interface TradeResult {
  trade: Trade;
  unfilled_quantity: number;
  cash: number;
}

export interface Position {
  ticker: string;
  side: Side;
  market_title: string;
  quantity: number;
  avg_cost: number | null;
  cost_basis: number;
  mark_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
  status: "open" | "settled";
}

export interface Portfolio {
  cash: number;
  positions_value: number;
  equity: number;
  starting_cash: number;
  total_pnl: number;
  positions: Position[];
}

const TOKEN_KEY = "fomoshi_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: stay signed in for this tab only */
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return `Request failed (${status})`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError("Can't reach the Fomoshi server. Is the backend running?", 0);
  }
  const body = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && token) {
      setToken(null);
      window.dispatchEvent(new Event("fomoshi:signed-out"));
    }
    throw new ApiError(errorMessage(body, res.status), res.status);
  }
  return body as T;
}

const post = <T>(path: string, data: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(data) });

export const api = {
  register: (username: string, password: string) =>
    post<{ access_token: string }>("/api/auth/register", { username, password }),
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username, password }),
    }),
  me: () => request<User>("/api/auth/me"),

  events: (params: { q?: string; category?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.category) qs.set("category", params.category);
    const query = qs.toString();
    return request<{ events: EventSummary[]; cursor: string | null }>(
      `/api/markets${query ? `?${query}` : ""}`,
    );
  },
  market: (ticker: string) => request<MarketDetail>(`/api/markets/${encodeURIComponent(ticker)}`),
  orderbook: (ticker: string) =>
    request<OrderBook>(`/api/markets/${encodeURIComponent(ticker)}/orderbook`),

  preview: (body: TradeRequest) => post<Preview>("/api/trades/preview", body),
  trade: (body: TradeRequest) => post<TradeResult>("/api/trades", body),
  trades: () => request<Trade[]>("/api/trades"),
  portfolio: () => request<Portfolio>("/api/portfolio"),
};
