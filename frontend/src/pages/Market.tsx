import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  api,
  type Action,
  type OrderBook,
  type Position,
  type Preview,
  type Side,
  type TradeRequest,
} from "../api";
import { useAuth } from "../auth";
import { ChanceBar } from "../components/ChanceBar";
import { cents, chance, closesIn, count, money, percent, signedMoney } from "../format";
import { usePolling } from "../usePolling";

export function Market() {
  const { ticker = "" } = useParams();
  const { user } = useAuth();
  const market = usePolling(() => api.market(ticker), 5_000, [ticker]);
  const book = usePolling(() => api.orderbook(ticker), 5_000, [ticker]);
  const holdings = usePolling(
    async () => (user ? (await api.portfolio()).positions.filter((p) => p.ticker === ticker) : []),
    0,
    [ticker, user?.id],
  );
  const [side, setSide] = useState<Side>("yes");

  if (market.error && !market.data) {
    return (
      <p className="notice notice--error">
        {market.error}. <Link to="/">Back to markets</Link>
      </p>
    );
  }
  const m = market.data;
  if (!m) return <p className="notice">Loading market…</p>;
  const p = chance(m);

  return (
    <div className="market">
      <div className="market__main">
        <Link to="/" className="back-link">
          All markets
        </Link>
        <p className="market__event">{m.event_title}</p>
        <h1 className="market__title">{m.label}</h1>

        <div className="market__chance">
          <span className="market__pct">{percent(p)}</span>
          <span className="market__pct-label">chance of yes</span>
        </div>
        <ChanceBar chance={p} size="lg" />

        <dl className="stats">
          <div>
            <dt>Volume</dt>
            <dd>{count(m.volume)}</dd>
          </div>
          <div>
            <dt>Last 24 hours</dt>
            <dd>{count(m.volume_24h)}</dd>
          </div>
          <div>
            <dt>Open interest</dt>
            <dd>{count(m.open_interest)}</dd>
          </div>
          <div>
            <dt>Closing</dt>
            <dd>{closesIn(m.close_time).replace(/^Closes /, "") || "—"}</dd>
          </div>
        </dl>

        <BookLadder book={book.data} side={side} />

        {m.rules_primary && (
          <section className="rules">
            <h2>How this market resolves</h2>
            <p>{m.rules_primary}</p>
          </section>
        )}
      </div>

      <aside className="market__side">
        <TradeTicket
          ticker={ticker}
          side={side}
          onSideChange={setSide}
          prices={{ yes: m.yes_ask, no: m.no_ask, yesBid: m.yes_bid, noBid: m.no_bid }}
          holdings={holdings.data ?? []}
          tradable={m.status === "active" || m.status === "open"}
          onTraded={() => {
            holdings.reload();
            book.reload();
          }}
        />
      </aside>
    </div>
  );
}

function BookLadder({ book, side }: { book: OrderBook | null; side: Side }) {
  if (!book) return null;
  const asks = (side === "yes" ? book.yes_asks : book.no_asks).slice(0, 6).reverse();
  const bids = (side === "yes" ? book.yes_bids : book.no_bids).slice(0, 6);
  const max = Math.max(1, ...asks.map((l) => l.quantity), ...bids.map((l) => l.quantity));
  const spread = asks.length && bids.length ? asks[asks.length - 1].price - bids[0].price : null;

  return (
    <section className="ladder" aria-label={`Order book for ${side.toUpperCase()}`}>
      <h2>Order book for {side === "yes" ? "Yes" : "No"}</h2>
      <div className="ladder__head">
        <span>Price</span>
        <span>Contracts</span>
      </div>
      {asks.length === 0 && <p className="ladder__empty">No one is selling right now</p>}
      {asks.map((l) => (
        <div className="ladder__row ladder__row--ask" key={`a${l.price}`}>
          <span>{cents(l.price)}</span>
          <span>{l.quantity.toLocaleString()}</span>
          <i style={{ width: `${(l.quantity / max) * 100}%` }} />
        </div>
      ))}
      <div className="ladder__spread">
        {spread != null ? `Spread ${cents(spread)}` : "No spread yet"}
      </div>
      {bids.map((l) => (
        <div className="ladder__row ladder__row--bid" key={`b${l.price}`}>
          <span>{cents(l.price)}</span>
          <span>{l.quantity.toLocaleString()}</span>
          <i style={{ width: `${(l.quantity / max) * 100}%` }} />
        </div>
      ))}
      {bids.length === 0 && <p className="ladder__empty">No one is buying right now</p>}
      <p className="ladder__note">Asks above the line are what you pay to buy. Bids below are what you get to sell.</p>
    </section>
  );
}

interface TicketProps {
  ticker: string;
  side: Side;
  onSideChange: (s: Side) => void;
  prices: { yes: number | null; no: number | null; yesBid: number | null; noBid: number | null };
  holdings: Position[];
  tradable: boolean;
  onTraded: () => void;
}

function TradeTicket({ ticker, side, onSideChange, prices, holdings, tradable, onTraded }: TicketProps) {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [action, setAction] = useState<Action>("buy");
  const [quantity, setQuantity] = useState("10");
  const [limit, setLimit] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const qty = Number.parseInt(quantity, 10);
  const limitPrice = limit ? Number(limit) / 100 : undefined;
  const validLimit = limitPrice === undefined || (limitPrice > 0 && limitPrice < 1);
  const held = holdings.find((h) => h.side === side && h.status === "open")?.quantity ?? 0;
  const request: TradeRequest | null =
    qty > 0 && validLimit ? { ticker, side, action, quantity: qty, limit_price: limitPrice } : null;
  const requestKey = JSON.stringify(request);

  useEffect(() => {
    setPreview(null);
    if (!request) return;
    const id = window.setTimeout(() => {
      api.preview(request).then(setPreview).catch(() => setPreview(null));
    }, 250);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!user) {
      navigate("/login", { state: { from: location.pathname } });
      return;
    }
    if (!request) return;
    setBusy(true);
    setMessage(null);
    try {
      const r = await api.trade(request);
      const verb = action === "buy" ? "Bought" : "Sold";
      const leftover = r.unfilled_quantity ? ` ${r.unfilled_quantity} couldn’t fill at your price.` : "";
      setMessage({
        kind: "ok",
        text: `${verb} ${r.trade.quantity} ${side.toUpperCase()} at ${cents(r.trade.avg_price)} average.${leftover}`,
      });
      await refresh();
      onTraded();
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Order failed" });
    } finally {
      setBusy(false);
    }
  };

  const priceFor = (s: Side) =>
    action === "buy" ? (s === "yes" ? prices.yes : prices.no) : s === "yes" ? prices.yesBid : prices.noBid;

  return (
    <form className={`panel ticket ticket--${side}`} onSubmit={submit}>
      <div className="segmented" role="group" aria-label="Buy or sell">
        <button type="button" aria-pressed={action === "buy"} onClick={() => setAction("buy")}>
          Buy
        </button>
        <button type="button" aria-pressed={action === "sell"} onClick={() => setAction("sell")}>
          Sell
        </button>
      </div>

      <div className="side-picker" role="group" aria-label="Outcome">
        {(["yes", "no"] as const).map((s) => (
          <button
            key={s}
            type="button"
            className={`side-picker__${s}`}
            aria-pressed={side === s}
            onClick={() => onSideChange(s)}
          >
            <span>{s === "yes" ? "Yes" : "No"}</span>
            <strong>{cents(priceFor(s))}</strong>
          </button>
        ))}
      </div>

      <label className="field">
        <span>Contracts</span>
        <input
          inputMode="numeric"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value.replace(/\D/g, ""))}
          aria-describedby="held-note"
        />
        {action === "sell" && (
          <small id="held-note">
            You hold {held} {side.toUpperCase()}
            {held > 0 && (
              <>
                {" · "}
                <button type="button" className="link-button" onClick={() => setQuantity(String(held))}>
                  Sell all
                </button>
              </>
            )}
          </small>
        )}
      </label>

      <label className="field">
        <span>Limit price in cents (optional)</span>
        <input
          inputMode="decimal"
          placeholder={action === "buy" ? "Pay at most…" : "Accept at least…"}
          value={limit}
          onChange={(e) => setLimit(e.target.value.replace(/[^\d.]/g, ""))}
          aria-invalid={!validLimit}
        />
        {!validLimit && <small className="form-error">Enter a price between 1 and 99</small>}
      </label>

      <dl className="ticket__summary">
        <div>
          <dt>Average price</dt>
          <dd>{preview?.avg_price != null ? cents(preview.avg_price) : "—"}</dd>
        </div>
        <div>
          <dt>{action === "buy" ? "You pay" : "You receive"}</dt>
          <dd>{preview ? money(preview.total) : "—"}</dd>
        </div>
        {action === "buy" && (
          <div className="ticket__payout">
            <dt>Payout if {side === "yes" ? "Yes" : "No"} wins</dt>
            <dd>
              {preview ? money(preview.max_payout) : "—"}
              {preview && preview.total > 0 && (
                <small> {signedMoney(preview.max_payout - preview.total)}</small>
              )}
            </dd>
          </div>
        )}
      </dl>
      {preview && preview.unfilled_quantity > 0 && (
        <p className="ticket__warn">
          Only {preview.filled_quantity} of {qty} can fill right now. The rest will be cancelled.
        </p>
      )}

      {message && (
        <p className={message.kind === "ok" ? "form-ok" : "form-error"} role="status">
          {message.text}
        </p>
      )}

      <button
        className="button button--block"
        disabled={busy || !tradable || (user != null && (!request || preview?.filled_quantity === 0))}
      >
        {!tradable
          ? "Market closed"
          : !user
            ? "Sign in to trade"
            : busy
              ? "Placing order…"
              : `${action === "buy" ? "Buy" : "Sell"} ${side === "yes" ? "Yes" : "No"}`}
      </button>
      {user && <p className="ticket__cash">Cash available: {money(user.cash)}</p>}
    </form>
  );
}
