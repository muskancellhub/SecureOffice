# deploy/ — server provisioning artifacts

Two things live here: the **serving stack** (nginx + systemd, below) and the
**logging pipeline** (design: [docs/LOGGING_PLAN.md](../docs/LOGGING_PLAN.md)).
Nothing here runs in dev — on a dev machine the app writes RFC 5424 lines
directly to `./logs/dev/` (`LOG_SINK=file`, the default), and Vite's
`server.proxy` stands in for nginx.

| Path | Installed at | Purpose |
|---|---|---|
| `nginx/secureoffice2.conf` | `/etc/nginx/conf.d/secureoffice2.conf` | The single public entrypoint: static SPA + `/api` reverse proxy on port 80 |
| `systemd/secureoffice2-api.service` | `/etc/systemd/system/` | uvicorn on 127.0.0.1:8000, restarted on failure |
| `rsyslog.d/secureoffice.conf` | `/etc/rsyslog.d/30-secureoffice.conf` | Route local0 (app) / local1 (audit) to `/var/log/secureoffice/*.log`; disable rate limiting for audit; 64k message size |
| `logrotate.d/secureoffice` | `/etc/logrotate.d/secureoffice` | Daily rename + gzip + HUP rsyslog |
| `scripts/secureoffice-rotate-logs` | `/usr/local/bin/secureoffice-rotate-logs` | Wrapper: logrotate → verify gzip → dated archive folders → retention (90d app / 365d audit) |
| `cron.d/secureoffice-logs` | `/etc/cron.d/secureoffice-logs` | Runs the wrapper daily at 00:05 as root |
| `scripts/provision-logging.sh` | run once via sudo / EC2 user-data | Installs all of the above, creates dirs + `<repo>/logs` symlink, smoke-tests both streams |
| `aws/iam-policy-log-archive.json` | EC2 instance role | Minimal List+Put for the archive sync — no delete/read, so the box can't erase shipped audit history |
| `aws/s3-lifecycle.json` | log-archive bucket | Glacier at 90d for both streams; app expires at 400d, audit never |

## Serving stack (nginx + uvicorn)

The browser talks to **one origin**: nginx on port 80. It serves the built SPA
and forwards `/api/*` to uvicorn on loopback. That is what lets the frontend
bundle contain no hostname (`frontend/src/api/config.ts`), so the same build
artifact runs on localhost, here, and behind a domain later.

```
browser ──http──► nginx :80 ──┬── /        → frontend/dist  (try_files → index.html)
                              └── /api/*   → 127.0.0.1:8000 (uvicorn, prefix stripped)
```

### Install

Edit the paths marked `EDIT ME` in both files first, then:

```bash
sudo cp deploy/nginx/secureoffice2.conf /etc/nginx/conf.d/secureoffice2.conf
sudo cp deploy/systemd/secureoffice2-api.service /etc/systemd/system/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl daemon-reload && sudo systemctl enable --now secureoffice2-api
```

Removing `sites-enabled/default` matters — the stock default site also claims
port 80 and will shadow this one.

### Required `backend/.env` settings on the server

| Setting | Value | Why |
|---|---|---|
| `TRUSTED_PROXY_COUNT` | `1` | **Not optional.** Defaults to `0`, which makes the rate limiter and the audit log see `127.0.0.1` for every request — one shared 120-req/min bucket for the whole internet, and an access log with no real client IPs. |
| `BACKEND_CORS_ORIGINS` | `http://209.35.98.135` | Same-origin makes this mostly moot, but a stale `localhost:5173` is a trap for the next host added. |
| `FRONTEND_URL` | `http://209.35.98.135` | Where the OAuth callback redirects the browser after login. |
| `GOOGLE_REDIRECT_URI`<br>`MICROSOFT_REDIRECT_URI` | `http://209.35.98.135/api/auth/<provider>/callback` | Must also be registered in the provider console — see the caveat below. |
| `APP_ENV` | `staging` | **Not `production`** while on plain HTTP; see below. |
| `COOKIE_SECURE` | `false` | Required on HTTP, and the reason `APP_ENV` can't be `production`. |
| `LOG_SINK` / `LOG_LEVEL` | `syslog` / `INFO` | Per the logging pipeline below. |

### Build the frontend before deploying

```bash
cd frontend && npm run build
```

Leave `VITE_API_BASE_URL` unset so the bundle uses the relative `/api`. Verify
with `grep -r localhost frontend/dist` — it should return nothing (apart from
`VITE_GRAFANA_URL`, if you set it to an absolute origin).

### HTTP-only caveats

Serving over plain HTTP on a bare IP is **staging-grade, not production-grade**.
Three things do not work, and none of them are fixable in nginx:

1. **The app refuses to boot with `APP_ENV=production`.** `_assert_production_hardening`
   (`backend/app/main.py`) rejects `COOKIE_SECURE=false` because the refresh
   token would cross the wire in cleartext. That guard is correct — run as
   `staging` and treat the deployment accordingly.
2. **Square payments break.** The Web Payments SDK requires a secure context
   (HTTPS, or `localhost` exactly). The card form will not tokenize.
3. **Google / Microsoft OAuth break.** Both providers reject non-HTTPS redirect
   URIs for anything other than `localhost`. Email + OTP login still works.

All three clear the moment TLS is in front, which is a change to this nginx
config only. If a DNS name for the box is available, Let's Encrypt is the
shortest path to resolving all three at once.

## Logging pipeline

## Install (Linux server / EC2)

```bash
sudo deploy/scripts/provision-logging.sh
```

Then run the app with `LOG_SINK=syslog` (and `LOG_LEVEL=INFO`). Verify end to
end with a request and `tail -f /var/log/secureoffice/app.log`.

Force a rotation to test the archive path without waiting for midnight:

```bash
sudo /usr/local/bin/secureoffice-rotate-logs            # full run
sudo /usr/local/bin/secureoffice-rotate-logs --organize-only  # re-run archive/retention only
```

Archives land in `/var/log/secureoffice/archive/YYYY-MM-DD/<stream>-YYYY-MM-DD.log.gz`,
visible from the repo via the `logs/` symlink. Retention is tunable via
`APP_RETENTION_DAYS` / `AUDIT_RETENTION_DAYS` env vars in the cron file.

## Off-box durability (phase 5 — S3-archives-only)

Decision 2026-06-11: archives sync to S3 daily; live tail-based shipping
(CloudWatch / Fluent Bit) is deferred until there's a search/alerting need.
To enable at EC2 go-live:

1. Create a **versioned** S3 bucket; apply `aws/s3-lifecycle.json`.
2. Attach `aws/iam-policy-log-archive.json` (bucket name substituted) to the
   instance role; install the aws CLI.
3. Set `SECUREOFFICE_S3_BUCKET=<bucket>` in `/etc/cron.d/secureoffice-logs`.

The sync is idempotent (`aws s3 sync`), so missed days catch up on the next
run, and the job exits non-zero if a sync fails. Accepted residual risk of
S3-only: up to 24h of the newest logs die with the instance — revisit live
shipping if compliance needs a tighter RPO.
