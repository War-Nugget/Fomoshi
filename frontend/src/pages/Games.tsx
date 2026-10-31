import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type Game, type MarketSummary } from "../api";
import { cents, chance, clockTime, count, dayLabel, percent } from "../format";
import { usePolling } from "../usePolling";

const PAGE_SIZE = 24;
const MAX_SHOWN = 96; // the API's largest page
const REFRESH_MS = 3_000; // quicker than anywhere else on the site: in-game prices move fast
const TOP_LEAGUES = 10; // busiest leagues get chips; Kalshi lists 150+, the rest go in a menu

export function Games() {
  const [params, setParams] = useSearchParams();
  const league = params.get("league") ?? "";
  const [shown, setShown] = useState(PAGE_SIZE);
  const leagues = usePolling(() => api.gameLeagues(), 60_000);
  const games = usePolling(
    async () => ({ league, page: await api.games({ league, page_size: shown }) }),
    REFRESH_MS,
    [league, shown],
    { keepData: true }, // keep the cards on screen while "Show more" loads
  );
  // ...but never show the previous league's games after switching leagues
  const page = games.data?.league === league ? games.data.page : null;

  const pickLeague = (name: string) => {
    setShown(PAGE_SIZE);
    const next = new URLSearchParams(params);
    if (name) next.set("league", name);
    else next.delete("league");
    setParams(next, { replace: true });
  };

  const live = page?.games.filter((g) => g.live) ?? [];
  const days = byDay(page?.games.filter((g) => !g.live) ?? []);

  return (
    <>
      <div className="page-head">
        <h1>Games</h1>
      </div>
      <p className="page-lede">
        Live and upcoming matchups. Prices update every few seconds, and orders always fill at
        Kalshi’s current prices.
      </p>

      {leagues.data && leagues.data.length > 1 && (
        <div className="chips" role="group" aria-label="Filter by league">
          <button aria-pressed={!league} onClick={() => pickLeague("")}>
            All
          </button>
          {leagues.data.slice(0, TOP_LEAGUES).map((lg) => (
            <button key={lg.name} aria-pressed={league === lg.name} onClick={() => pickLeague(lg.name)}>
              {lg.name}
            </button>
          ))}
          {leagues.data.length > TOP_LEAGUES && (
            <select
              aria-label="More leagues"
              className="chips__more"
              value={leagues.data.slice(TOP_LEAGUES).some((lg) => lg.name === league) ? league : ""}
              onChange={(e) => pickLeague(e.target.value)}
            >
              <option value="">More leagues…</option>
              {leagues.data.slice(TOP_LEAGUES).map((lg) => (
                <option key={lg.name} value={lg.name}>
                  {lg.name} ({lg.count})
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {games.error && !page && <p className="notice notice--error">{games.error}</p>}
      {!page && !games.error && <p className="notice">Loading games…</p>}
      {page && page.games.length === 0 && (
        <p className="notice">No games scheduled right now. Check back closer to game time.</p>
      )}

      {live.length > 0 && (
        <section className="games-section" aria-labelledby="games-live">
          <h2 id="games-live" className="games-section__title">
            Live now
          </h2>
          <div className="game-grid">
            {live.map((g) => (
              <GameCard key={g.event_ticker} game={g} />
            ))}
          </div>
        </section>
      )}

      {days.map((day) => (
        <section key={day.label} className="games-section" aria-label={day.label}>
          <h2 className="games-section__title">{day.label}</h2>
          <div className="game-grid">
            {day.games.map((g) => (
              <GameCard key={g.event_ticker} game={g} />
            ))}
          </div>
        </section>
      ))}

      {page?.has_more && (
        <div className="load-more">
          {shown < MAX_SHOWN ? (
            <button className="button button--quiet" onClick={() => setShown(shown + PAGE_SIZE)}>
              Show more games
            </button>
          ) : (
            <p className="notice">Pick a league to see more games.</p>
          )}
        </div>
      )}
    </>
  );
}

/** Upcoming games arrive in start order, so consecutive runs share a day. */
function byDay(games: Game[]) {
  const days: { label: string; games: Game[] }[] = [];
  for (const g of games) {
    const label = dayLabel(g.start_time);
    if (days[days.length - 1]?.label !== label) days.push({ label, games: [] });
    days[days.length - 1].games.push(g);
  }
  return days;
}

function GameCard({ game }: { game: Game }) {
  const { team_a: a, team_b: b, tie } = game;
  return (
    <article className={`game${game.live ? " game--live" : ""}`}>
      <header className="game__head">
        {game.live ? (
          <span className="live-badge">Live</span>
        ) : (
          <time dateTime={game.start_time}>{clockTime(game.start_time)}</time>
        )}
        <span className="game__league">{game.league}</span>
      </header>
      <h3 className="game__title">
        <Link to={`/events/${game.event_ticker}`}>
          {a.label} <span className="game__vs">vs</span> {b.label}
        </Link>
      </h3>
      <ul className="game__sides">
        <SideRow market={a} />
        <SideRow market={b} />
        {tie && <SideRow market={tie} />}
      </ul>
      {game.volume_24h > 0 && <p className="game__meta">{count(game.volume_24h)} traded in 24h</p>}
    </article>
  );
}

function SideRow({ market }: { market: MarketSummary }) {
  const p = chance(market);
  return (
    <li>
      <Link
        to={`/markets/${market.ticker}`}
        className="game-side"
        aria-label={`${market.label}: ${percent(p)} chance, buy at ${cents(market.yes_ask)}`}
      >
        <span className="game-side__name">{market.label}</span>
        <span className="game-side__pct">{percent(p)}</span>
        <span className="price-tag price-tag--yes">Buy {cents(market.yes_ask)}</span>
      </Link>
    </li>
  );
}
