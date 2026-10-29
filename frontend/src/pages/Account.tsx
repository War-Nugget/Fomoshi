import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export function Account() {
  const { user, loading, signOut, startSession } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [deletePw, setDeletePw] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [delError, setDelError] = useState<string | null>(null);

  if (!loading && !user) return <Navigate to="/login" state={{ from: "/account", mode: "signin" }} replace />;
  if (!user) return <p className="notice">Loading…</p>;

  const changePassword = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await startSession((await api.changePassword(current, next)).access_token);
      setCurrent("");
      setNext("");
      setPwMsg({ ok: true, text: "Password changed. Other devices have been signed out." });
    } catch (err) {
      setPwMsg({ ok: false, text: err instanceof Error ? err.message : "Couldn’t change password" });
    }
  };

  const deleteAccount = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.deleteAccount(deletePw);
      signOut();
      navigate("/", { replace: true });
    } catch (err) {
      setDelError(err instanceof Error ? err.message : "Couldn’t delete account");
    }
  };

  return (
    <div className="account">
      <h1>Account</h1>
      <dl className="account__facts">
        <div>
          <dt>Username</dt>
          <dd>{user.username}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd>{user.email ?? "Not set"}</dd>
        </div>
      </dl>
      <button className="button button--quiet" onClick={() => { signOut(); navigate("/"); }}>
        Sign out
      </button>

      <form className="account__section" onSubmit={changePassword}>
        <h2>Change password</h2>
        <label className="field">
          <span>Current password</span>
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </label>
        <label className="field">
          <span>New password</span>
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={8} required />
          <small>At least 8 characters</small>
        </label>
        {pwMsg && <p className={pwMsg.ok ? "form-ok" : "form-error"} role="status">{pwMsg.text}</p>}
        <button className="button">Change password</button>
      </form>

      <section className="account__section account__danger">
        <h2>Delete account</h2>
        <p>This permanently removes your trades, positions, and league memberships. Leagues you own are deleted too.</p>
        {!confirmDelete ? (
          <button className="button button--danger" onClick={() => setConfirmDelete(true)}>
            Delete my account
          </button>
        ) : (
          <form onSubmit={deleteAccount}>
            <label className="field">
              <span>Enter your password to confirm</span>
              <input type="password" value={deletePw} onChange={(e) => setDeletePw(e.target.value)} autoComplete="current-password" required />
            </label>
            {delError && <p className="form-error" role="alert">{delError}</p>}
            <div className="button-row">
              <button className="button button--danger">Permanently delete</button>
              <button type="button" className="button button--quiet" onClick={() => setConfirmDelete(false)}>
                Keep my account
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
