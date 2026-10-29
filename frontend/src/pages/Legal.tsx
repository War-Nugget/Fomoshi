import { Link } from "react-router-dom";

// NOTE: These are starting templates written for a play-money hobby project.
// Have them reviewed before launch, and fill in the contact address.
const CONTACT = "support@your-domain.com";
const UPDATED = "October 2026";

export function Terms() {
  return (
    <article className="prose">
      <h1>Terms of use</h1>
      <p className="prose__updated">Last updated {UPDATED}</p>
      <h2>What Fomoshi is</h2>
      <p>
        Fomoshi is a simulator. You trade with play money that has no cash value. You can’t deposit
        money, withdraw money, buy more play money, or win prizes. Nothing on Fomoshi is financial,
        investment, or betting advice.
      </p>
      <h2>Who can use it</h2>
      <p>You must be at least 18 years old to create an account.</p>
      <h2>Your account</h2>
      <p>
        Keep your password private. One account per person. Usernames that impersonate others or
        are offensive may be changed or removed.
      </p>
      <h2>Market data</h2>
      <p>
        Prices and market information come from Kalshi’s public API and may be delayed or
        incorrect. Fomoshi is not affiliated with or endorsed by Kalshi. Simulated fills are
        estimates and don’t reflect real trades.
      </p>
      <h2>Fair use</h2>
      <p>
        Don’t abuse the service: no automated account creation, scraping, or attempts to disrupt
        it. We may reset balances, remove accounts, or change the game at any time.
      </p>
      <h2>No warranty</h2>
      <p>
        Fomoshi is provided as is, without warranties of any kind. To the fullest extent allowed by
        law, we aren’t liable for any losses arising from your use of it.
      </p>
      <h2>Contact</h2>
      <p>Questions: {CONTACT}</p>
    </article>
  );
}

export function Privacy() {
  return (
    <article className="prose">
      <h1>Privacy policy</h1>
      <p className="prose__updated">Last updated {UPDATED}</p>
      <h2>What we collect</h2>
      <ul>
        <li>Your username, email address, and a hashed (not readable) version of your password.</li>
        <li>Your simulated trades, positions, league memberships, and daily account value.</li>
        <li>Basic server logs, such as IP address and request times, to keep the service secure.</li>
      </ul>
      <h2>How we use it</h2>
      <p>
        To run your account, show leaderboards, send password-reset emails, and prevent abuse. Your
        username and account value appear on public leaderboards and in leagues you join. Your email
        is never shown to other players.
      </p>
      <h2>What we don’t do</h2>
      <p>We don’t sell your data or use it for advertising.</p>
      <h2>Service providers</h2>
      <p>
        We use hosting, database, and email providers to run Fomoshi. They process data only on our
        behalf.
      </p>
      <h2>Your choices</h2>
      <p>
        You can delete your account and its data at any time from your{" "}
        <Link to="/account">account page</Link>.
      </p>
      <h2>Contact</h2>
      <p>Questions or requests: {CONTACT}</p>
    </article>
  );
}

export function HowItWorks() {
  return (
    <article className="prose">
      <h1>How Fomoshi works</h1>
      <h2>Prices are probabilities</h2>
      <p>
        Every market asks a yes-or-no question. A contract pays $1 if its side is right and $0 if
        it’s wrong, so a YES price of 41¢ means traders put the chance at about 41%.
      </p>
      <h2>Your orders hit the real order book</h2>
      <p>
        When you buy, Fomoshi fills your order against Kalshi’s live offers, cheapest first. A large
        order can use up the best price and fill partly at worse ones, just like a real exchange.
        Anything that can’t fill right away, or would break your limit price, is cancelled.
      </p>
      <h2>Why YES + NO is about $1</h2>
      <p>
        Someone bidding 58¢ for NO is effectively offering to sell YES at 42¢. That’s why the YES ask
        and NO bid always add up to $1.
      </p>
      <h2>Settlement</h2>
      <p>
        When Kalshi decides a market, Fomoshi pays $1 per winning contract into your cash balance
        automatically, usually within a few minutes.
      </p>
      <h2>Account value</h2>
      <p>
        Your account value is your cash plus what your open positions could sell for right now (the
        best bid). That’s what the leaderboard ranks.
      </p>
      <p>
        <Link to="/markets">Browse markets</Link>
      </p>
    </article>
  );
}

export function NotFound() {
  return (
    <div className="prose">
      <h1>That page doesn’t exist</h1>
      <p>
        The link may be old, or the market may have been removed. <Link to="/markets">Browse markets</Link>
      </p>
    </div>
  );
}
