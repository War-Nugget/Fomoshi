// Typed wrapper around the Fomoshi API.

export type Side = "yes" | "no";
export type Action = "buy" | "sell";
export type ChartRange = "1d" | "1w" | "1m" | "all";
export type Sort = "trending" | "volume" | "closing" | "new";

export interface User {
  id: number;
  username: string;
  email: string | null;
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
  close_time: string | null;
  volume_24h: number;
  markets: MarketSummary[];
}

export interface EventsPage {
  events: EventSummary[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface MarketDetail extends MarketSummary {
  event_title: string;
  series_ticker: string;
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

export interface HistoryPoint {
  t: number;
  p: number;
}

export interface SeriesHistory {
  ticker: string;
  label: string;
  points: HistoryPoint[];
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
  market_title: string;
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

export interface LeaderRow {
  rank: number;
  username: string;
  equity: number;
  gain: number;
  gain_pct: number;
  is_you: boolean;
}

export interface Leaderboard {
  rows: LeaderRow[];
  you: LeaderRow | null;
  total_players: number;
}

export interface LeagueSummary {
  id: number;
  name: string;
  description: string;
  invite_code: string;
  member_count: number;
  is_owner: boolean;
  your_rank: number | null;
}

export interface LeagueDetail extends LeagueSummary {
  standings: LeaderRow[];
}

// In production the frontend may be served from a different host than the API.
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
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
  if (Array.isArray(detail) && detail[0]?.msg) {
    const field = Array.isArray(detail[0].loc) ? detail[0].loc.at(-1) : null;
    const msg = String(detail[0].msg).replace(/^String should/, "Should");
    return field && field !== "body" ? `${String(field)[0].toUpperCase()}${String(field).slice(1)}: ${msg}` : msg;
  }
  if (status === 429) return "Too many requests. Wait a moment and try again.";
  if (status >= 500) return "The server had a problem. Try again in a moment.";
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
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Can't reach Fomoshi right now. Check your connection.", 0);
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

const qs = (params: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") s.set(k, String(v));
  const out = s.toString();
  return out ? `?${out}` : "";
};

const enc = encodeURIComponent;

export const api = {
  register: (username: string, email: string, password: string) =>
    post<{ access_token: string }>("/api/auth/register", { username, email, password }),
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username, password }),
    }),
  me: () => request<User>("/api/auth/me"),
  forgotPassword: (email: string) => post<{ detail: string }>("/api/auth/forgot-password", { email }),
  resetPassword: (token: string, password: string) =>
    post<{ access_token: string }>("/api/auth/reset-password", { token, password }),
  changePassword: (current_password: string, new_password: string) =>
    post<{ access_token: string }>("/api/auth/change-password", { current_password, new_password }),
  deleteAccount: (password: string) => post<null>("/api/auth/delete-account", { password }),

  events: (p: { q?: string; category?: string; sort?: Sort; page?: number; page_size?: number } = {}) =>
    request<EventsPage>(`/api/markets${qs(p)}`),
  categories: () => request<{ name: string; count: number }[]>("/api/markets/categories"),
  event: (eventTicker: string) => request<EventSummary>(`/api/events/${enc(eventTicker)}`),
  eventHistory: (eventTicker: string, range: ChartRange) =>
    request<{ series: SeriesHistory[] }>(`/api/events/${enc(eventTicker)}/history${qs({ range })}`),
  market: (ticker: string) => request<MarketDetail>(`/api/markets/${enc(ticker)}`),
  orderbook: (ticker: string) => request<OrderBook>(`/api/markets/${enc(ticker)}/orderbook`),
  marketHistory: (ticker: string, range: ChartRange) =>
    request<{ points: HistoryPoint[] }>(`/api/markets/${enc(ticker)}/history${qs({ range })}`),

  preview: (body: TradeRequest) => post<Preview>("/api/trades/preview", body),
  trade: (body: TradeRequest) => post<TradeResult>("/api/trades", body),
  trades: (before_id?: number) => request<Trade[]>(`/api/trades${qs({ before_id, limit: 50 })}`),
  portfolio: () => request<Portfolio>("/api/portfolio"),
  equityHistory: () => request<{ day: string; equity: number }[]>("/api/portfolio/history"),

  leaderboard: () => request<Leaderboard>("/api/leaderboard"),
  leagues: () => request<LeagueSummary[]>("/api/leagues"),
  league: (id: number) => request<LeagueDetail>(`/api/leagues/${id}`),
  createLeague: (name: string, description: string) =>
    post<LeagueDetail>("/api/leagues", { name, description }),
  joinLeague: (invite_code: string) => post<LeagueDetail>("/api/leagues/join", { invite_code }),
  leaveLeague: (id: number) => request<null>(`/api/leagues/${id}/membership`, { method: "DELETE" }),
};
