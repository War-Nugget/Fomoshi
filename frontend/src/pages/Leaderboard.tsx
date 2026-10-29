import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type LeaderRow } from "../api";
import { useAuth } from "../auth";
import { money, pnlClass, signedMoney } from "../format";
import { usePolling } from "../usePolling";

export function Leaderboard() {
  const { user } = useAuth();
  const board = usePolling(() => api.leaderboard(), 60_000, [user?.id]);

  return (
    <div className="leaderboard">
      <div className="leaderboard__main">
        <h1>Leaderboard</h1>
        <p className="page-lede">Everyone starts with $1,000. Ranked by account value: cash plus what your positions could sell for now.</p>
        {board.error && <p className="notice notice--error">{board.error}</p>}
        {!board.data && !board.error && <p className="notice">Loading…</p>}
        {board.data && board.data.rows.length === 0 && <p className="notice">No players yet. Be the first.</p>}
        {board.data && board.data.rows.length > 0 && (
          <>
            <Standings rows={board.data.rows} gainLabel="Since start" />
            {board.data.you && !board.data.rows.some((r) => r.is_you) && (
              <div className="your-rank">
                <Standings rows={[board.data.you]} gainLabel="Since start" hideHead />
              </div>
            )}
            <p className="table-note">{board.data.total_players.toLocaleString()} players</p>
          </>
        )}
      </div>
      <aside className="leaderboard__side">
        <Leagues />
      </aside>
    </div>
  );
}

export function Standings({ rows, gainLabel, hideHead }: { rows: LeaderRow[]; gainLabel: string; hideHead?: boolean }) {
  return (
    <div className="table-scroll">
      <table className="standings">
        {!hideHead && (
          <thead>
            <tr>
              <th className="num">Rank</th>
              <th>Player</th>
              <th className="num">Account value</th>
              <th className="num">{gainLabel}</th>
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.rank}-${r.username}`} className={r.is_you ? "is-you" : undefined}>
              <td className="num standings__rank">{r.rank}</td>
              <td>
                {r.username}
                {r.is_you && <span className="you-tag">You</span>}
              </td>
              <td className="num">{money(r.equity)}</td>
              <td className={`num ${pnlClass(r.gain)}`}>
                {signedMoney(r.gain)} <small>({r.gain_pct > 0 ? "+" : ""}{r.gain_pct.toFixed(1)}%)</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Leagues() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const leagues = usePolling(() => (user ? api.leagues() : Promise.resolve([])), 0, [user?.id]);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!user) {
    return (
      <section className="panel leagues">
        <h2>Leagues</h2>
        <p>Compete privately with friends. Everyone is ranked by how much they’ve gained since joining.</p>
        <Link to="/login" state={{ from: "/leaderboard" }} className="button button--block">
          Sign up to start a league
        </Link>
      </section>
    );
  }

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const lg = await api.createLeague(name, "");
      navigate(`/leagues/${lg.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t create league");
    }
  };
  const join = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const lg = await api.joinLeague(code);
      navigate(`/leagues/${lg.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn’t join league");
    }
  };

  return (
    <section className="panel leagues">
      <h2>Your leagues</h2>
      {leagues.data && leagues.data.length === 0 && <p>You’re not in any leagues yet. Start one and share the code.</p>}
      {leagues.data && leagues.data.length > 0 && (
        <ul className="league-list">
          {leagues.data.map((lg) => (
            <li key={lg.id}>
              <Link to={`/leagues/${lg.id}`}>{lg.name}</Link>
              <span>
                {lg.your_rank ? `#${lg.your_rank} of ${lg.member_count}` : `${lg.member_count} members`}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={create} className="inline-form">
        <label className="field">
          <span>New league name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={60} required />
        </label>
        <button className="button">Create</button>
      </form>
      <form onSubmit={join} className="inline-form">
        <label className="field">
          <span>Invite code</span>
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} minLength={4} maxLength={12} autoCapitalize="characters" required />
        </label>
        <button className="button button--quiet">Join</button>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
    </section>
  );
}
