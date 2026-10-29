import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="panel auth-form" onSubmit={submit}>
        <h1>Reset your password</h1>
        {sent ? (
          <p className="form-ok" role="status">
            If {email} has an account, we’ve sent a link to reset the password. It expires in an hour.
          </p>
        ) : (
          <>
            <p className="auth-form__lede">Enter the email on your account and we’ll send you a reset link.</p>
            <label className="field">
              <span>Email</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            </label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="button button--block" disabled={busy}>
              {busy ? "Sending…" : "Send reset link"}
            </button>
          </>
        )}
        <div className="auth-form__links">
          <Link to="/login" state={{ mode: "signin" }}>Back to sign in</Link>
        </div>
      </form>
    </div>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { startSession } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirm) return setError("The two passwords don’t match");
    setBusy(true);
    setError(null);
    try {
      await startSession((await api.resetPassword(token, password)).access_token);
      navigate("/portfolio", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <div className="auth-page">
        <div className="panel auth-form">
          <h1>This link is incomplete</h1>
          <p className="auth-form__lede">Open the link from your email again, or ask for a new one.</p>
          <Link to="/forgot-password" className="button button--block">Send a new link</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <form className="panel auth-form" onSubmit={submit}>
        <h1>Choose a new password</h1>
        <p className="auth-form__lede">This signs you out on every other device.</p>
        <label className="field">
          <span>New password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" minLength={8} required />
          <small>At least 8 characters</small>
        </label>
        <label className="field">
          <span>Type it again</span>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button button--block" disabled={busy}>
          {busy ? "Saving…" : "Save new password"}
        </button>
        {error?.includes("expired") && (
          <div className="auth-form__links">
            <Link to="/forgot-password">Send a new link</Link>
          </div>
        )}
      </form>
    </div>
  );
}
