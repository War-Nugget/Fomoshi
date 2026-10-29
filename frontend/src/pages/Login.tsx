import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export function Login() {
  const { user, signIn, signUp } = useAuth();
  const location = useLocation();
  const state = location.state as { from?: string; mode?: "signin" | "signup" } | null;
  const [mode, setMode] = useState<"signin" | "signup">(state?.mode ?? "signup");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const from = state?.from ?? "/markets";

  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") await signUp(username, email, password);
      else await signIn(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="panel auth-form" onSubmit={submit}>
        <h1>{mode === "signup" ? "Create your account" : "Welcome back"}</h1>
        <p className="auth-form__lede">
          {mode === "signup"
            ? "You’ll start with $1,000 in play money."
            : "Sign in with your username or email."}
        </p>

        <label className="field">
          <span>{mode === "signup" ? "Username" : "Username or email"}</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            {...(mode === "signup"
              ? { minLength: 3, maxLength: 30, pattern: "[A-Za-z0-9_]+", title: "Letters, numbers, and underscores" }
              : {})}
            required
          />
          {mode === "signup" && <small>Shown on leaderboards. Letters, numbers, and underscores.</small>}
        </label>

        {mode === "signup" && (
          <label className="field">
            <span>Email</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            <small>Only used to reset your password.</small>
          </label>
        )}

        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            minLength={mode === "signup" ? 8 : undefined}
            required
          />
          {mode === "signup" && <small>At least 8 characters</small>}
        </label>

        {mode === "signup" && (
          <label className="checkbox">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} required />
            <span>
              I’m 18 or older and agree to the <Link to="/terms">terms</Link> and{" "}
              <Link to="/privacy">privacy policy</Link>.
            </span>
          </label>
        )}

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="button button--block" disabled={busy}>
          {busy ? "One moment…" : mode === "signup" ? "Create account" : "Sign in"}
        </button>

        <div className="auth-form__links">
          {mode === "signup" ? (
            <span>
              Have an account?{" "}
              <button type="button" className="link-button" onClick={() => setMode("signin")}>
                Sign in
              </button>
            </span>
          ) : (
            <>
              <Link to="/forgot-password">Forgot your password?</Link>
              <span>
                New here?{" "}
                <button type="button" className="link-button" onClick={() => setMode("signup")}>
                  Create an account
                </button>
              </span>
            </>
          )}
        </div>
      </form>
    </div>
  );
}
