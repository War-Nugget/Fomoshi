import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import { money } from "../format";

export function Layout() {
  const { user, signOut } = useAuth();
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="wordmark" aria-label="Fomoshi home">
          <span className="wordmark__mark" aria-hidden="true" />
          fomoshi
        </Link>
        <nav className="topbar__nav">
          <NavLink to="/" end>
            Markets
          </NavLink>
          <NavLink to="/portfolio">Portfolio</NavLink>
        </nav>
        <div className="topbar__account">
          {user ? (
            <>
              <span className="topbar__cash" title="Cash available to trade">
                {money(user.cash)}
              </span>
              <button className="link-button" onClick={signOut}>
                Sign out
              </button>
            </>
          ) : (
            <Link to="/login" className="button button--small">
              Sign in
            </Link>
          )}
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
      <footer className="footer">
        Play money only. Prices come from Kalshi’s public market data. Fomoshi is not affiliated
        with Kalshi.
      </footer>
    </div>
  );
}
