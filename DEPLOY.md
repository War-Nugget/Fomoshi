# Deploying Fomoshi

Two ways to go live. Option A costs nothing to start; option B gives you full control.

Before either one:

1. **Read Kalshi's developer terms** for using their public market data on a public site, and keep the "not affiliated" notice in the footer.
2. **Fill in the contact email** in `frontend/src/pages/Legal.tsx`, and have the terms and privacy text reviewed.
3. **Pick an email provider** for password resets. Any SMTP service works (Resend, Postmark, Brevo, Mailgun, or SendGrid). You'll need SMTP host, username, password, and a verified "from" address.

---

## Option A: Render (free tier to start)

`render.yaml` creates four things: Postgres, Key Value (Redis), the API, and the static frontend.

1. Push the repo to GitHub.
2. In Render: **New → Blueprint**, pick the repo, and approve the resources.
3. When the API finishes deploying, note its URL (for example `https://fomoshi-api.onrender.com`). If it differs from that name, edit the `/api/*` rewrite at the bottom of `render.yaml` to point at your API URL, then push.
4. Note the frontend URL (for example `https://fomoshi-web.onrender.com`). On the **fomoshi-api** service, set these environment variables:
   - `APP_URL` = the frontend URL
   - `CORS_ORIGINS` = the frontend URL
   - `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` from your email provider
   - `SENTRY_DSN` (optional)
5. Open the frontend URL. The first market sync starts as soon as the API boots; `GET /api/health` should report `"database": true`.

**About the free tier:** free web services sleep after a period of no traffic and take a little while to wake up. While the API sleeps, the in-process worker pauses too, so settlements happen when it wakes. That's fine for a portfolio project. For always-on settlement, move to a paid instance and uncomment the `fomoshi-worker` service in `render.yaml` (then set `RUN_WORKER_IN_PROCESS=false` on the API). Free Render Postgres databases also expire after a limited time, so check Render's current limits or point `DATABASE_URL` at a free Neon or Supabase database instead.

**Custom domain:** add it under the frontend service's settings, then update `APP_URL` and `CORS_ORIGINS` to match.

---

## Option B: any server with Docker

Works on a small VPS (DigitalOcean, Hetzner, Lightsail, and others) or a home server.

```bash
git clone https://github.com/War-Nugget/fomoshi.git && cd fomoshi
cp .env.example .env
# edit .env: SECRET_KEY, POSTGRES_PASSWORD, APP_URL, CORS_ORIGINS, SMTP_*
docker compose up -d --build
```

This runs Postgres, Redis, the API, a separate worker, and nginx on port 8080.

**HTTPS:** put a reverse proxy in front of port 8080. The simplest is [Caddy](https://caddyserver.com), which gets certificates automatically:

```
fomoshi.example.com {
    reverse_proxy localhost:8080
}
```

**Updates:** `git pull && docker compose up -d --build`. Migrations run automatically when the API starts.

**Backups:** `docker compose exec db pg_dump -U fomoshi fomoshi > backup.sql` (run it on a schedule with cron).

---

## Environment variables

| Variable | Needed | What it does |
|---|---|---|
| `ENVIRONMENT` | yes | `production` turns on safety checks and HSTS |
| `SECRET_KEY` | yes | Signs login tokens. At least 32 random characters |
| `DATABASE_URL` | yes | Postgres connection string (`postgres://` and `postgresql://` both work) |
| `REDIS_URL` | recommended | Shared cache and rate limits. Without it, each process keeps its own |
| `APP_URL` | yes | Public site URL, used in password-reset emails |
| `CORS_ORIGINS` | yes | Comma-separated origins allowed to call the API |
| `KALSHI_MODE` | no | `live` (default) or `mock` |
| `RUN_WORKER_IN_PROCESS` | no | `true` runs the worker inside the API. A lock keeps it to one copy |
| `WEB_CONCURRENCY` | no | API worker processes (default 2) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | for resets | Email delivery |
| `SENTRY_DSN` | no | Error tracking |
| `MARKET_SYNC_INTERVAL_SECONDS` | no | How often to copy Kalshi's catalog (default 300) |
| `SETTLEMENT_INTERVAL_SECONDS` | no | How often to check for settled markets (default 60) |
| `STARTING_CASH` | no | Play money for new accounts (default 1000) |

## Checklist after going live

- [ ] Sign up, place a trade, and check the portfolio
- [ ] Request a password reset and confirm the email arrives
- [ ] Watch the API logs for `catalog sync: N events` every few minutes
- [ ] Set up uptime monitoring on `/api/health` (UptimeRobot, Better Stack, or similar)
- [ ] Add the live URL to your GitHub repo, README, and resume
