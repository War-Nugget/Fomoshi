import { Link, Navigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { EventBlock } from "../components/EventBlock";
import { usePolling } from "../usePolling";

export function Landing() {
  const { user, loading } = useAuth();
  const trending = usePolling(() => api.events({ sort: "trending", page_size: 3 }), 60_000);

  if (!loading && user) return <Navigate to="/markets" replace />;

  return (
    <div className="landing">
      <section className="hero">
        <h1>Bet on what happens next, with money that isn’t real.</h1>
        <p>
          Fomoshi copies live prediction markets from Kalshi, real prices and all. You get $1,000 in
          play money to trade YES or NO, then see how good your calls actually are.
        </p>
        <div className="hero__actions">
          <Link to="/login" className="button">
            Start with $1,000
          </Link>
          <Link to="/markets" className="button button--quiet">
            Browse markets
          </Link>
        </div>
      </section>

      <section className="explainer" aria-labelledby="how">
        <h2 id="how">How a market works</h2>
        <div className="explainer__demo" aria-hidden="true">
          <div className="explainer__row">
            <span className="explainer__yes">YES costs 41¢</span>
            <span className="explainer__no">NO costs 59¢</span>
          </div>
          <div className="chance-bar chance-bar--lg">
            <span className="chance-bar__yes" style={{ flexGrow: 0.41 }} />
            <span className="chance-bar__no" style={{ flexGrow: 0.59 }} />
          </div>
        </div>
        <ol className="steps">
          <li>
            <strong>The price is the odds.</strong> A YES contract at 41¢ means traders think there’s
            about a 41% chance it happens.
          </li>
          <li>
            <strong>Pick a side.</strong> Buy YES if you think the odds are too low, NO if you think
            they’re too high.
          </li>
          <li>
            <strong>Get paid $1 if you’re right.</strong> Each winning contract pays $1 when the market
            settles. You can also sell early if the price moves your way.
          </li>
        </ol>
      </section>

      <section aria-labelledby="trending">
        <div className="section-head">
          <h2 id="trending">Trending right now</h2>
          <Link to="/markets">See all markets</Link>
        </div>
        {trending.data ? (
          <div className="event-list">
            {trending.data.events.map((e) => (
              <EventBlock key={e.event_ticker} event={e} />
            ))}
          </div>
        ) : (
          <p className="notice">{trending.error ?? "Loading markets…"}</p>
        )}
      </section>

      <section className="landing__cta">
        <h2>Start a league with friends</h2>
        <p>Make a private leaderboard, share the code, and find out who in your group actually knows things.</p>
        <Link to="/login" className="button">
          Create a free account
        </Link>
      </section>
    </div>
  );
}
