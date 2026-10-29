import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ChartRange } from "../api";
import { OutcomeRow } from "../components/EventBlock";
import { LINE_COLORS, PriceChart, RangePicker, type ChartLine } from "../components/PriceChart";
import { closesIn, count } from "../format";
import { usePolling } from "../usePolling";

export function Event() {
  const { eventTicker = "" } = useParams();
  const [range, setRange] = useState<ChartRange>("1w");
  const event = usePolling(() => api.event(eventTicker), 15_000, [eventTicker]);
  const history = usePolling(() => api.eventHistory(eventTicker, range), 60_000, [eventTicker, range]);

  const lines: ChartLine[] = useMemo(
    () =>
      (history.data?.series ?? []).map((s, i) => ({
        id: s.ticker,
        label: s.label,
        color: LINE_COLORS[i % LINE_COLORS.length],
        points: s.points.map((p) => ({ time: p.t, value: p.p })),
      })),
    [history.data],
  );

  if (event.error && !event.data) {
    return (
      <p className="notice notice--error">
        {event.error}. <Link to="/markets">Back to markets</Link>
      </p>
    );
  }
  const e = event.data;
  if (!e) return <p className="notice">Loading…</p>;
  const open = e.markets.filter((m) => m.status === "active" || m.status === "open");
  const closed = e.markets.filter((m) => !open.includes(m));

  return (
    <div className="event-page">
      <Link to="/markets" className="back-link">
        All markets
      </Link>
      <p className="market__event">{e.category}</p>
      <h1 className="event-page__title">{e.title}</h1>
      <p className="event-page__meta">
        {count(e.volume_24h)} traded in the last day
        {e.close_time ? ` · ${closesIn(e.close_time)}` : ""}
      </p>

      <div className="chart-head">
        <h2>Chance over time</h2>
        <RangePicker value={range} onChange={setRange} />
      </div>
      <PriceChart
        lines={lines}
        format="percent"
        height={320}
        loading={!history.data}
        ariaLabel={`Chance over time for ${e.title}`}
      />
      {lines.length > 0 && open.length > lines.length && (
        <p className="table-note">The chart shows the {lines.length} most likely outcomes.</p>
      )}

      <h2 className="section-title">Outcomes</h2>
      <ul className="outcomes">
        {open.map((m) => (
          <OutcomeRow key={m.ticker} market={m} showLabel />
        ))}
      </ul>
      {closed.length > 0 && (
        <>
          <h2 className="section-title">Closed outcomes</h2>
          <ul className="outcomes">
            {closed.map((m) => (
              <OutcomeRow key={m.ticker} market={m} showLabel />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
