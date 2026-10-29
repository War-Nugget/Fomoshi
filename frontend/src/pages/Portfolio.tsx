import { useEffect, useMemo, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api, type Trade } from "../api";
import { useAuth } from "../auth";
import { PriceChart, type ChartLine } from "../components/PriceChart";
import { cents, money, pnlClass, signedMoney } from "../format";
import { usePolling } from "../usePolling";

const SideBadge = ({ side }: { side: "yes" | "no" }) => (
  <span className={`side-badge side-badge--${side}`}>{side === "yes" ? "Yes" : "No"}</span>
);

export function Portfolio() {
  const { user, loading } = useAuth();
  const portfolio = usePolling(() => api.portfolio(), 15_000, [user?.id]);
  const equity = usePolling(() => api.equityHistory(), 0, [user?.id]);

  const lines: ChartLine[] = useMemo(
    () => [
      {
        id: "equity",
        label: "Account value",
        color: "var(--ink)",
        points: (equity.data ?? []).map((p) => ({ time: p.day, value: p.equity })),
      },
    ],
    [equity.data],
  );

  if (!loading && !user) return <Navigate to="/login" state={{ from: "/portfolio" }} replace />;
  const pf = portfolio.data;
  if (portfolio.error && !pf) return <p className="notice notice--error">{portfolio.error}</p>;
  if (!pf) return <p className="notice">Loading portfolio…</p>;

  const open = pf.positions.filter((p) => p.status === "open");
  const settled = pf.positions.filter((p) => p.status === "settled");

  return (
    <>
      <section className="summary">
        <div className="summary__equity">
          <span>Account value</span>
          <strong>{money(pf.equity)}</strong>
          <em className={pnlClass(pf.total_pnl)}>
            {signedMoney(pf.total_pnl)} since you started with {money(pf.starting_cash)}
          </em>
        </div>
        <dl className="stats">
          <div>
            <dt>Cash</dt>
            <dd>{money(pf.cash)}</dd>
          </div>
          <div>
            <dt>In positions</dt>
            <dd>{money(pf.positions_value)}</dd>
          </div>
        </dl>
      </section>

      <section className="table-section">
        <PriceChart
          lines={lines}
          format="money"
          height={200}
          loading={!equity.data}
          emptyText="Your account value chart starts filling in after your first full day."
          ariaLabel="Account value by day"
        />
      </section>

      <section className="table-section">
        <h2>Open positions</h2>
        {open.length === 0 ? (
          <p className="notice">
            You don’t hold anything yet. <Link to="/markets">Pick a market</Link> to place your first trade.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Side</th>
                  <th className="num">Contracts</th>
                  <th className="num">Avg cost</th>
                  <th className="num">Now</th>
                  <th className="num">Value</th>
                  <th className="num">Gain or loss</th>
                </tr>
              </thead>
              <tbody>
                {open.map((p) => (
                  <tr key={`${p.ticker}-${p.side}`}>
                    <td>
                      <Link to={`/markets/${p.ticker}`}>{p.market_title}</Link>
                    </td>
                    <td>
                      <SideBadge side={p.side} />
                    </td>
                    <td className="num">{p.quantity}</td>
                    <td className="num">{cents(p.avg_cost)}</td>
                    <td className="num">{cents(p.mark_price)}</td>
                    <td className="num">{money(p.market_value)}</td>
                    <td className={`num ${pnlClass(p.unrealized_pnl)}`}>{signedMoney(p.unrealized_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="table-note">“Now” is the best bid, the price you could sell at this moment.</p>
      </section>

      {settled.length > 0 && (
        <section className="table-section">
          <h2>Settled</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Side</th>
                  <th className="num">Result</th>
                </tr>
              </thead>
              <tbody>
                {settled.map((p) => (
                  <tr key={`${p.ticker}-${p.side}`}>
                    <td>
                      <Link to={`/markets/${p.ticker}`}>{p.market_title}</Link>
                    </td>
                    <td>
                      <SideBadge side={p.side} />
                    </td>
                    <td className={`num ${pnlClass(p.realized_pnl)}`}>{signedMoney(p.realized_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <TradeHistory userId={user?.id} />
    </>
  );
}

function TradeHistory({ userId }: { userId?: number }) {
  const [trades, setTrades] = useState<Trade[] | null>(null);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.trades().then((t) => {
      setTrades(t);
      setMore(t.length === 50);
    }).catch(() => setTrades([]));
  }, [userId]);

  const loadOlder = async () => {
    if (!trades?.length) return;
    setBusy(true);
    try {
      const older = await api.trades(trades[trades.length - 1].id);
      setTrades([...trades, ...older]);
      setMore(older.length === 50);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="table-section">
      <h2>Trade history</h2>
      {trades && trades.length === 0 && <p className="notice">No trades yet.</p>}
      {trades && trades.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Trade</th>
                <th>Market</th>
                <th className="num">Price</th>
                <th className="num">Total</th>
                <th className="num">Realized</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id}>
                  <td>{new Date(t.created_at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}</td>
                  <td>
                    {t.action === "settle" ? "Settled" : t.action === "buy" ? "Bought" : "Sold"} {t.quantity}{" "}
                    <SideBadge side={t.side} />
                  </td>
                  <td>
                    <Link to={`/markets/${t.ticker}`}>{t.market_title || t.ticker}</Link>
                  </td>
                  <td className="num">{t.action === "settle" ? money(t.avg_price) : cents(t.avg_price)}</td>
                  <td className="num">{money(t.total)}</td>
                  <td className={`num ${pnlClass(t.realized_pnl)}`}>{t.action === "buy" ? "" : signedMoney(t.realized_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {more && (
        <div className="load-more">
          <button className="button button--quiet" onClick={loadOlder} disabled={busy}>
            {busy ? "Loading…" : "Show older trades"}
          </button>
        </div>
      )}
    </section>
  );
}
