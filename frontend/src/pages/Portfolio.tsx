import { Link, Navigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { cents, money, pnlClass, signedMoney } from "../format";
import { usePolling } from "../usePolling";

export function Portfolio() {
  const { user, loading } = useAuth();
  const portfolio = usePolling(() => api.portfolio(), 15_000, [user?.id]);
  const trades = usePolling(() => api.trades(), 0, [user?.id]);

  if (!loading && !user) return <Navigate to="/login" state={{ from: "/portfolio" }} replace />;
  const pf = portfolio.data;
  if (portfolio.error && !pf) return <p className="notice notice--error">{portfolio.error}</p>;
  if (!pf) return <p className="notice">Loading portfolio…</p>;

  const titles = new Map(pf.positions.map((p) => [p.ticker, p.market_title]));
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
        <h2>Open positions</h2>
        {open.length === 0 ? (
          <p className="notice">
            You don’t hold anything yet. <Link to="/">Pick a market</Link> to place your first trade.
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
                      <span className={`side-badge side-badge--${p.side}`}>{p.side === "yes" ? "Yes" : "No"}</span>
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
                    <td>{p.market_title}</td>
                    <td>
                      <span className={`side-badge side-badge--${p.side}`}>{p.side === "yes" ? "Yes" : "No"}</span>
                    </td>
                    <td className={`num ${pnlClass(p.realized_pnl)}`}>{signedMoney(p.realized_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="table-section">
        <h2>Trade history</h2>
        {trades.data && trades.data.length === 0 && <p className="notice">No trades yet.</p>}
        {trades.data && trades.data.length > 0 && (
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
                {trades.data.map((t) => (
                  <tr key={t.id}>
                    <td>{new Date(t.created_at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}</td>
                    <td>
                      {t.action === "settle" ? "Settled" : t.action === "buy" ? "Bought" : "Sold"} {t.quantity}{" "}
                      <span className={`side-badge side-badge--${t.side}`}>{t.side === "yes" ? "Yes" : "No"}</span>
                    </td>
                    <td>
                      <Link to={`/markets/${t.ticker}`}>{titles.get(t.ticker) || t.ticker}</Link>
                    </td>
                    <td className="num">{t.action === "settle" ? money(t.avg_price) : cents(t.avg_price)}</td>
                    <td className="num">{money(t.total)}</td>
                    <td className={`num ${pnlClass(t.realized_pnl)}`}>
                      {t.action === "buy" ? "" : signedMoney(t.realized_pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
