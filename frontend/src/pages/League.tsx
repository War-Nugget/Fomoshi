import { useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { usePolling } from "../usePolling";
import { Standings } from "./Leaderboard";

export function League() {
  const { id = "" } = useParams();
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const league = usePolling(() => api.league(Number(id)), 60_000, [id, user?.id]);
  const [copied, setCopied] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);

  if (!loading && !user) return <Navigate to="/login" state={{ from: `/leagues/${id}`, mode: "signin" }} replace />;
  if (league.error && !league.data) {
    return (
      <p className="notice notice--error">
        {league.error}. <Link to="/leaderboard">Back to leaderboard</Link>
      </p>
    );
  }
  const lg = league.data;
  if (!lg) return <p className="notice">Loading…</p>;

  const invite = `${window.location.origin}/leaderboard`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`Join my Fomoshi league "${lg.name}" with code ${lg.invite_code} at ${invite}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard blocked; the code is visible anyway */
    }
  };

  const leave = async () => {
    await api.leaveLeague(lg.id);
    navigate("/leaderboard");
  };

  return (
    <div className="league">
      <Link to="/leaderboard" className="back-link">
        Leaderboard
      </Link>
      <h1>{lg.name}</h1>
      <div className="invite">
        <span>Invite code</span>
        <strong className="invite__code">{lg.invite_code}</strong>
        <button className="button button--small" onClick={copy}>
          {copied ? "Copied" : "Copy invite"}
        </button>
      </div>
      <p className="page-lede">Ranked by gain since each person joined, so latecomers can still win.</p>
      <Standings rows={lg.standings} gainLabel="Since joining" />

      <div className="league__leave">
        {!confirmLeave ? (
          <button className="link-button" onClick={() => setConfirmLeave(true)}>
            {lg.is_owner ? "Delete this league" : "Leave this league"}
          </button>
        ) : (
          <div className="button-row">
            <span>{lg.is_owner ? "Delete the league for everyone?" : "Leave this league?"}</span>
            <button className="button button--danger button--small" onClick={leave}>
              {lg.is_owner ? "Delete league" : "Leave"}
            </button>
            <button className="button button--quiet button--small" onClick={() => setConfirmLeave(false)}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
