import { useState } from "react";
import { Link } from "react-router-dom";
import type { EventSummary, MarketSummary } from "../api";
import { cents, chance, closesIn, count, percent } from "../format";
import { ChanceBar } from "./ChanceBar";

const OUTCOMES_SHOWN = 4;

export function EventBlock({ event }: { event: EventSummary }) {
  const [expanded, setExpanded] = useState(false);
  const markets = expanded ? event.markets : event.markets.slice(0, OUTCOMES_SHOWN);
  const single = event.markets.length === 1;
  return (
    <section className="event">
      <header className="event__head">
        <h2>
          {single ? (
            event.title
          ) : (
            <Link to={`/events/${event.event_ticker}`} className="event__link">
              {event.title}
            </Link>
          )}
        </h2>
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

export function OutcomeRow({ market, showLabel }: { market: MarketSummary; showLabel: boolean }) {
  const p = chance(market);
  const settled = market.result === "yes" || market.result === "no";
  return (
    <li>
      <Link to={`/markets/${market.ticker}`} className="outcome">
        <span className="outcome__label">{showLabel ? market.label : "Chance of yes"}</span>
        <span className="outcome__pct">{settled ? (market.result === "yes" ? "Yes" : "No") : percent(p)}</span>
        <ChanceBar chance={settled ? (market.result === "yes" ? 1 : 0) : p} />
        <span className="outcome__prices">
          {settled ? (
            <span className="price-tag">Settled</span>
          ) : (
            <>
              <span className="price-tag price-tag--yes">Yes {cents(market.yes_ask)}</span>
              <span className="price-tag price-tag--no">No {cents(market.no_ask)}</span>
            </>
          )}
        </span>
        <span className="outcome__meta">
          {count(market.volume)} traded{market.close_time ? ` · ${closesIn(market.close_time)}` : ""}
        </span>
      </Link>
    </li>
  );
}
