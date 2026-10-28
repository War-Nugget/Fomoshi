import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type EventSummary, type MarketSummary } from "../api";
import { ChanceBar } from "../components/ChanceBar";
import { cents, chance, closesIn, count, percent } from "../format";
import { usePolling } from "../usePolling";

const OUTCOMES_SHOWN = 4;

export function Markets() {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState<string | null>(null);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 300);
    return () => window.clearTimeout(id);
  }, [query]);

  const { data, error } = usePolling(() => api.events({ q: debounced }), 30_000, [debounced]);
  const events = data?.events ?? [];

  const categories = useMemo(
    () => [...new Set(events.map((e) => e.category))].sort(),
    [events],
  );
  const shown = category ? events.filter((e) => e.category === category) : events;

  return (
    <>
      <div className="page-head">
        <h1>Markets</h1>
        <input
          className="search"
          type="search"
          placeholder="Search markets"
          aria-label="Search markets"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {categories.length > 1 && (
        <div className="chips" role="group" aria-label="Filter by category">
          <button aria-pressed={category === null} onClick={() => setCategory(null)}>
            All
          </button>
          {categories.map((c) => (
            <button key={c} aria-pressed={category === c} onClick={() => setCategory(c)}>
              {c}
            </button>
          ))}
        </div>
      )}

      {error && <p className="notice notice--error">{error}</p>}
      {!data && !error && <p className="notice">Loading markets…</p>}
      {data && shown.length === 0 && (
        <p className="notice">
          {debounced ? `No open markets match “${debounced}”.` : "No open markets right now."}
        </p>
      )}

      <div className="event-list">
        {shown.map((e) => (
          <EventBlock key={e.event_ticker} event={e} />
        ))}
      </div>
    </>
  );
}

function EventBlock({ event }: { event: EventSummary }) {
  const [expanded, setExpanded] = useState(false);
  const markets = expanded ? event.markets : event.markets.slice(0, OUTCOMES_SHOWN);
  const single = event.markets.length === 1;
  return (
    <section className="event">
      <header className="event__head">
        <h2>{event.title}</h2>
        <span className="event__meta">{event.category}</span>
      </header>
      <ul className="outcomes">
        {markets.map((m) => (
          <OutcomeRow key={m.ticker} market={m} showLabel={!single} />
        ))}
      </ul>
      {event.markets.length > OUTCOMES_SHOWN && (
        <button className="link-button event__more" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show fewer outcomes" : `Show all ${event.markets.length} outcomes`}
        </button>
      )}
    </section>
  );
}

function OutcomeRow({ market, showLabel }: { market: MarketSummary; showLabel: boolean }) {
  const p = chance(market);
  return (
    <li>
      <Link to={`/markets/${market.ticker}`} className="outcome">
        <span className="outcome__label">{showLabel ? market.label : "Chance of yes"}</span>
        <span className="outcome__pct">{percent(p)}</span>
        <ChanceBar chance={p} />
        <span className="outcome__prices">
          <span className="price-tag price-tag--yes">Yes {cents(market.yes_ask)}</span>
          <span className="price-tag price-tag--no">No {cents(market.no_ask)}</span>
        </span>
        <span className="outcome__meta">
          {count(market.volume)} traded · {closesIn(market.close_time)}
        </span>
      </Link>
    </li>
  );
}
