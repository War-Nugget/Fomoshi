import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export function Login() {
  const { user, signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signup");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";

  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await (mode === "signup" ? signUp : signIn)(username, password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <div className="login__pitch">
        <h1>Bet on what happens next, with money that isn’t real.</h1>
        <p>
          Every account starts with $1,000 in play money. Trade YES or NO on live prediction
          markets at real prices, and see how good your calls actually are.
        </p>
        <ChanceExample />
      </div>

      <form className="panel login__form" onSubmit={submit}>
        <div className="segmented" role="tablist" aria-label="Account">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signup"}
            onClick={() => setMode("signup")}
          >
            Create account
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "signin"}
            onClick={() => setMode("signin")}
          >
            Sign in
          </button>
        </div>
        <label className="field">
          <span>Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            minLength={3}
            maxLength={30}
            pattern="[A-Za-z0-9_]+"
            title="Letters, numbers, and underscores"
            required
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "signup" ? "new-password" : "current-password"}
            minLength={8}
            required
          />
          {mode === "signup" && <small>At least 8 characters</small>}
        </label>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="button button--block" disabled={busy}>
          {busy ? "One moment…" : mode === "signup" ? "Create account" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

function ChanceExample() {
  return (
    <div className="login__example" aria-hidden="true">
      <div className="login__example-row">
        <span>YES costs 41¢</span>
        <span>NO costs 59¢</span>
      </div>
      <div className="chance-bar chance-bar--lg">
        <span className="chance-bar__yes" style={{ flexGrow: 0.41 }} />
        <span className="chance-bar__no" style={{ flexGrow: 0.59 }} />
      </div>
      <p>Whichever side is right pays $1 per contract. The price is the crowd’s odds.</p>
    </div>
  );
}
