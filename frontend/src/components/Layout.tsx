import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { useAuth } from "../auth";
import { money } from "../format";

export function Layout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0); // newer browsers return a Promise here; don't return it
  }, [pathname]);

  return (
    <div className="shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="topbar">
        <Link to="/" className="wordmark" aria-label="Fomoshi home">
          <span className="wordmark__mark" aria-hidden="true" />
          fomoshi
        </Link>
        <nav className="topbar__nav" aria-label="Main">
          <NavLink to="/markets">Markets</NavLink>
          <NavLink to="/games">Games</NavLink>
          <NavLink to="/leaderboard">Leaderboard</NavLink>
          <NavLink to="/portfolio">Portfolio</NavLink>
        </nav>
        <div className="topbar__account">
          {user ? (
            <>
              <span className="topbar__cash" title="Cash available to trade">
                {money(user.cash)}
              </span>
              <NavLink to="/account" className="topbar__user">
                {user.username}
              </NavLink>
            </>
          ) : (
            <>
              <Link to="/login" state={{ mode: "signin" }} className="topbar__signin">
                Sign in
              </Link>
              <Link to="/login" className="button button--small">
                Sign up
              </Link>
            </>
          )}
        </div>
      </header>
      <main className="page" id="main">
        <Outlet />
      </main>
      <footer className="footer">
        <p>
          Play money only. Prices come from Kalshi’s public market data. Fomoshi is not affiliated
          with Kalshi.
        </p>
        <nav aria-label="Legal">
          <Link to="/how-it-works">How it works</Link>
          <Link to="/terms">Terms</Link>
          <Link to="/privacy">Privacy</Link>
        </nav>
      </footer>
    </div>
  );
}
