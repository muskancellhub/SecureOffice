# Logging System — Design Plan

**Project:** SecureOffice2 backend (FastAPI + PostgreSQL)
**Goal:** the project currently has no logging system. This plan introduces one: all logging (audit + application) emitted in **RFC 5424 syslog format** via Python's logging/syslog APIs, written in real time under `/var/log`, and archived daily by a cron job into dated, compressed folders under the project root `logs/` directory. Logs are **not** stored in the database.

---

## 1. Requirements

1. Syslog format per RFC 5424 (https://datatracker.ietf.org/doc/html/rfc5424).
2. Real-time logs written under `/var/log`.
3. Daily cron job compresses the previous day's log files and stores them in a dated folder under `<project root>/logs/`.
4. Written through Python's syslog API.
5. Use syslog severity levels (RFC 5424 defines 8, numbered 0–7) with a mapping we define (§2.2).
6. No setuid scripts — explained and an alternative recommended in §5.4.

## 2. Syslog primer (RFC 5424)

### 2.1 Message format

```
<PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
```

Example audit event:

```
<141>1 2026-06-10T14:32:01.123456Z api-01 secureoffice2 4242 user_role_changed
  [audit@99999 request_id="5f0c…" tenant_id="ab12…" user_id="cd34…" actor_role="ADMIN"
   ip="203.0.113.7" ua="Mozilla/5.0…" endpoint="PATCH /users/{user_id}/role"
   status="success" old_role="USER" new_role="ADMIN"] role changed by admin
```

- **PRI** = `facility × 8 + severity`. Above: facility local1 (17) × 8 + notice (5) = 141.
- **TIMESTAMP** — RFC 3339 / ISO 8601, timezone-aware UTC, microsecond precision. The same ISO date convention (`YYYY-MM-DD`) is used for archive folder names.
- **APP-NAME** = `secureoffice2`; **PROCID** = worker PID.
- **MSGID** = the event/action name (`user_login_failed`, `quote_converted`, …) — the primary machine-filterable field.
- **STRUCTURED-DATA** — RFC-standard key=value section. One SD element `[audit@<enterprise-number> …]` carries the common fields (request_id, tenant_id, user_id, ip, user_agent, endpoint, status) plus event-specific keys. Values escaped per RFC (`"`, `\`, `]`).
- **MSG** — short human-readable summary.

### 2.2 Severities (0–7) and our mapping — design decision

| # | Severity | Our usage |
|---|---|---|
| 0 | Emergency | Never emitted by the app (system-wide failure; reserved for the OS) |
| 1 | Alert | Reserved: future tamper/attack detection (e.g., auth-failure thresholds) |
| 2 | Critical | App cannot function: DB unreachable, production-hardening assertion failed at startup |
| 3 | Error | Unhandled 5xx (`server_error`), integration sync hard failures, logger-internal failures |
| 4 | Warning | Security-relevant failures: `user_login_failed`, `otp_verify_failed`, `access_denied`, `rate_limit_exceeded`, Stripe signature failures |
| 5 | Notice | **Default for successful audit events** (RFC: "normal but significant"): logins, role changes, quote/order/billing/pricing mutations |
| 6 | Informational | Request access-log lines; audited admin reads (`user_list_viewed`, `billing_overview_viewed`) |
| 7 | Debug | Developer diagnostics; suppressed outside dev via `LOG_LEVEL` |

### 2.3 Facilities — separating audit from app logs

Facilities are syslog's routing key. Two "local use" facilities:

- **local0 (16)** → **application logs**: access lines, errors, timings, integration chatter. For developers/ops.
- **local1 (17)** → **audit events**: who did what, when, from where. For security/compliance.

rsyslog routes by facility into separate files, so the two streams never mix even though both share one transport. They stay correlated through `request_id`.

(Aside: Linux's own `auditd` is a different thing — a kernel subsystem with its own format in `/var/log/audit/`, bypassing syslog. We don't use it; we follow the syslog convention for app-level audit trails: dedicated facility + MSGID + structured data, stricter file permissions, longer retention.)

## 3. Architecture

```
FastAPI app (per worker)
 │
 ├── Python logging (std lib)
 │     ├── logger "app"   → SyslogHandler  facility=local0
 │     └── logger "audit" → SyslogHandler  facility=local1
 │                │  RFC 5424 formatter (+ redaction filter, contextvars enrichment)
 │                ▼
 │        /dev/log (unix socket)
 │                ▼
 │            rsyslog daemon
 │     ┌──────────┴──────────┐
 │     ▼                     ▼
 │  /var/log/secureoffice/app.log     /var/log/secureoffice/audit.log   (live, real-time)
 │
 └── (dev/container fallback: RFC 5424 lines via WatchedFileHandler directly to the same paths)

      cron (daily, 00:05, runs as root)
        1. rotate: move app.log/audit.log → *-YYYY-MM-DD.log ; HUP rsyslog
        2. gzip the rotated files (verify with gzip -t)
        3. store → <project root>/logs/YYYY-MM-DD/
                      ├── app-2026-06-10.log.gz
                      └── audit-2026-06-10.log.gz
```

- **Python API:** primary = `logging.handlers.SysLogHandler(address='/dev/log')` with a custom RFC 5424 formatter (std-lib default emits the older RFC 3164-style format, so the formatter is ours). The std-lib `syslog` module is the alternative but is process-global with no formatter/filter pipeline; `logging` + `SysLogHandler` keeps audit and app logging in one framework. Dev/container fallback: same formatter via `WatchedFileHandler` straight to files.
- **Two std-lib gotchas the implementation must handle:**
  1. Python's `logging` has **no NOTICE level** (levels jump INFO=20 → WARNING=30), yet notice is our default audit severity (§2.2). Register a custom level — `logging.addLevelName(25, "NOTICE")` — and map it in both the handler's `priority_map` and the formatter's severity map; otherwise every successful audit event silently degrades to info or warning.
  2. `SysLogHandler` computes and prepends `<PRI>` itself from facility + priority. The custom formatter must therefore emit only the **post-PRI portion** (`1 TIMESTAMP HOSTNAME …`) when attached to `SysLogHandler`, or PRI gets double-encoded. The `file` sink's formatter, by contrast, writes the full line including PRI.
- **Why route through rsyslog in prod instead of writing files directly:** the app needs no write access to `/var/log` (permissions, §5), writes are line-atomic across multiple uvicorn workers, and forwarding to a remote syslog server/SIEM later is a config change, not a code change.

## 4. Code changes (high level — no code)

### 4.1 Request context

- **`RequestContextMiddleware`** (new, registered just inside CORS): generates `request_id` (UUID4; honor inbound `X-Request-Id` only from trusted proxies), resolves `client_ip` (extract `_resolve_client_ip` from `rate_limit.py` into a shared helper so rate limiting and logging use identical logic), captures `user_agent`. Stores all of it in `contextvars` so the loggers read it without passing parameters through every call. Emits the access-log line (info/local0) on the way out and sets the `X-Request-Id` response header.

### 4.2 Audit logger

- **`app/services/audit_logger.py`** (new): single write path — `audit.log(action, status='success', severity=None, target=None, **fields)`. Builds the STRUCTURED-DATA element from request context + supplied fields, maps severity per §2.2 (overridable per call), and **never raises into the request** (logging failure → stderr last resort; an outage in logging must not break checkout).
- **Redaction inside the logger, not at call sites:** recursive, case-insensitive key denylist (`password`, `token`, `secret`, `api_key`, `otp`, `card_number`, `authorization`, …) → `[REDACTED]`; card data only ever as last4 + brand. Applied to both facilities so neither audit nor app logs can leak credentials (e.g., Zabbix config updates log `url_set=true`, never the password).
- **Log-injection hygiene:** SD-value escaping per RFC + newline stripping, so user-controlled strings (emails, names) cannot forge log lines.

### 4.3 Central hooks (zero per-route work)

- `ForbiddenError` handler → `access_denied` (warning) with `endpoint_attempted` + `required_permission` (carried on the exception; `AuthorizationService.require` is the single raise site).
- `RateLimitMiddleware` 429 branch → `rate_limit_exceeded` (warning) with endpoint + request count.
- Unhandled-exception handler / `AppError` ≥500 → `server_error` (error) with `error_code` + `request_id`. Stack traces go to local0 only, never into audit structured data.

### 4.4 Application logging (local0)

- **`app/core/logging_config.py`** (new): central setup at startup — RFC 5424 formatter, severity map, redaction filter, handlers per environment (SyslogHandler in prod, file/console in dev), `LOG_LEVEL` env var. Route `uvicorn.access`/`uvicorn.error` through the same pipeline (disable uvicorn's default access log; the middleware's access line carries `request_id` instead).
- Existing ad-hoc `logging.getLogger(__name__)` calls across services inherit this config for free; move `main.py`'s in-function `import logging` to module level.

### 4.5 Environment-driven sink selection (no code change between dev and prod)

The handler is the only environment-specific piece, chosen by config at startup (12-factor, same pattern as `DATABASE_URL`):

| Env var | Dev (macOS laptop) | Prod (Linux server) |
|---|---|---|
| `LOG_SINK` | `file` → `WatchedFileHandler` | `syslog` → `SysLogHandler('/dev/log')` |
| `LOG_DIR` | `./logs/dev/` (project-local, gitignored, deletable) | n/a (rsyslog owns paths) |
| `LOG_LEVEL` | `DEBUG` | `INFO` |

Everything above the handler — RFC 5424 formatter, severity map, redaction, contextvars, every `audit.log(...)` call — is identical in all environments. Note macOS has no rsyslog (its syslog socket is `/var/run/syslog`, and `/var/log` needs sudo), so the `file` sink is the standard dev mode; logs on a dev machine are local to that machine and throwaway. rsyslog routing and the cron job exist only on the server (provisioning, not code).

Current state of the repo: no top-level `logs/` directory exists and `.gitignore` has no entry for it. Both are created in **phase 1** (not phase 4), because the dev file sink writes `./logs/dev/` from day one.

### 4.6 Touched-file summary

| Area | File | Change |
|---|---|---|
| Core | `app/core/logging_config.py` (new) | loggers, RFC 5424 formatter, severity map, redaction filter |
| Core | `app/core/request_context.py` (new) | contextvars + shared `resolve_client_ip` |
| Middleware | `app/middleware/request_context.py` (new) | context capture, access log, X-Request-Id |
| Middleware | `app/middleware/rate_limit.py` | emit `rate_limit_exceeded`; shared IP resolver |
| Service | `app/services/audit_logger.py` (new) | audit write path + redaction |
| Errors | `app/core/exceptions.py`, `app/main.py` | permission info on `ForbiddenError`; handlers emit `access_denied`/`server_error`; register middleware + config |
| Routes/services | per §6 | explicit `audit.log(...)` calls at mutation points |
| Ops | `deploy/rsyslog.d/secureoffice.conf` (new) | route local0/local1 → live files |
| Ops | `scripts/rotate_logs` + cron entry (new) | §5 rotation/archival |
| Tests | `backend/tests/` | formatter/redaction unit tests; per-event emission tests |

## 5. Storage, rotation, archival, permissions

### 5.1 Live files

- `/var/log/secureoffice/`, owned `syslog:adm`, mode `0750`; files `0640`. The app process has **no write access** — only rsyslog writes.
- Optional hardening: `chattr +a` (append-only) on `audit.log`.

### 5.2 Daily cron job

System crontab (root), daily at 00:05:

1. Rename `app.log` → `app-YYYY-MM-DD.log` (yesterday's date), same for `audit.log`; HUP rsyslog to reopen fresh files — no lines lost mid-rotation.
2. `gzip -9`; verify with `gzip -t` before removing originals.
3. Move into `<project root>/logs/YYYY-MM-DD/` (ISO 8601 date, consistent with RFC 5424's ISO timestamps). Archive ownership `root:root`, mode `0640` — readable by the app group, not modifiable or deletable by anyone but root. That's the tamper-resistance mechanism in a file-based design.
4. Retention: drop (or ship off-box) archive folders older than N days — suggest 90 for app, 365 for audit, configurable.

**Recommendation:** implement steps 1–3 as a `logrotate` config (`daily`, `dateext`, `compress`, `olddir`, postrotate HUP) invoked by the daily cron — same outcome, but logrotate already handles the race-prone parts (partial writes, missed days, re-runs) correctly.

**Archive location — adopted approach (override if needed):** archiving *into the project root* (`<repo>/logs/`) means archives disappear if the deploy directory is wiped/redeployed, and the folder must be in `.gitignore` so logs are never committed. The conventional layout is live logs in `/var/log/secureoffice/` and archives in `/var/log/secureoffice/archive/YYYY-MM-DD/` (logrotate `olddir` pattern). The plan therefore archives to `/var/log/secureoffice/archive/` and creates a symlink `<repo>/logs → /var/log/secureoffice/archive` — satisfies "visible under the project root" without tying log survival to the deploy directory.

### 5.3 File naming

`<stream>-YYYY-MM-DD.log.gz` inside `logs/YYYY-MM-DD/`. RFC 5424 standardizes the timestamp *inside messages* (RFC 3339); there is no RFC-mandated filename convention — ISO 8601 dates are the de-facto standard and what we use.

### 5.4 Why not a setuid script

A setuid executable runs with the file owner's privileges (e.g., root) regardless of who launches it. It was floated as a way for a non-root app user to manage root-owned log files. Rejected because:

1. The Linux kernel **ignores the setuid bit on interpreter scripts** (`#!` files) — it only works on compiled binaries — so a "setuid script" largely doesn't function.
2. Setuid-root programs are a classic privilege-escalation surface; security review flags them by default.
3. Nothing needs it in this design: the app never writes log files (rsyslog does), and rotation runs as root via the system crontab.

If a manually-triggered rotation is wanted, expose the root-owned script through a narrow `sudoers` entry (`appuser ALL=(root) NOPASSWD: /usr/local/bin/secureoffice-rotate`) — auditable and scoped.

### 5.5 Hosting: EC2 considerations

The target deployment is EC2 (Linux VM), where this design applies directly: stock AMIs ship rsyslog; the rsyslog conf, `/var/log/secureoffice` provisioning, and root cron entry go into instance provisioning (user-data/Ansible); the app runs as a non-root systemd service with `LOG_SINK=syslog`.

Note the repo currently has **no provisioning artifacts at all** — no `deploy/` directory, systemd unit, Dockerfile, or Procfile. The `deploy/rsyslog.d/` conf and cron/logrotate entries in §4.6 will be the repo's first such files, and the EC2 provisioning story (user-data/Ansible) is greenfield work, not an edit to something existing.

**EC2-specific risk — instances are disposable.** All logs (live + archives) sit on the instance's EBS volume; a terminate/replace/redeploy erases them, audit trail included. On EC2 this is the expected lifecycle, not an edge case, so off-box shipping should move from "later" into the initial deployment:

- **Shipping is tail-based and vendor-agnostic:** because rsyslog writes plain files, any shipper can tail them (read new lines as they're appended) — CloudWatch agent, Fluent Bit, Vector, Filebeat, promtail — forwarding to whatever platform is chosen (CloudWatch, Loki, ELK, Datadog, remote syslog). The platform decision can be deferred; the design doesn't change either way, and the agent install is pure ops config with zero app changes. If CloudWatch is chosen: agent + instance IAM role (no credentials in code), retention policies and alarms (e.g., spike of `user_login_failed`) come for free.
- **Durable archives:** the daily cron's final step can additionally `aws s3 cp` the gzipped files to a bucket (lifecycle rules → Glacier for cheap long-term retention), making archives survive the instance.
- Until shipping is in place, treat instance termination as audit-trail loss — acceptable for a staging box, not for production.

## 6. Event catalog (facility local1)

Policy: **every state-changing endpoint emits an audit event; security outcomes are captured centrally; reads are audited only when they expose sensitive/admin data.** Catalog browsing, self-reads, and the LLM chat endpoints (`/chatbot/ask`, `/intake/chat`, `/anam/*`) are app-log (local0) only; `/health` is excluded from both. The `integration_sync_logs` DB table is operational sync data, not logging — it stays.

Events are emitted from the **service layer**, where old/new values are naturally in scope. Within one action, the structured-data keys are kept consistent (one emit site per action + typed payloads).

| Category | Actions (MSGID) | Severity |
|---|---|---|
| Auth | `user_signup`, `vendor_signup`, `user_login` (method=password/otp), `user_logout`, `otp_requested`, `otp_verified`, `token_refresh`, `oauth_login` (provider, new_user_created), `super_admin_setup_link_sent`, `super_admin_credentials_changed` (flow=setup_token/admin_set) | notice |
| Auth failures | `user_login_failed` (email_attempted, reason), `otp_verify_failed` (attempts_remaining) | warning |
| User mgmt | `user_created`, `user_invited`, `user_role_changed` (old/new), `user_permissions_changed` (added/removed) | notice |
| Audited reads | `user_list_viewed`, `permission_catalog_viewed`, `billing_overview_viewed`, `tenant_list_viewed` | info |
| Cart | `cart_item_added`, `cart_item_updated` (old/new qty), `cart_item_removed`, `service_attached_to_device` | notice |
| Quotes | `quote_created` (also covers /component, /bundle, /generate variants via `source` field), `quote_updated`, `quote_sent`, `quote_accepted`, `quote_converted` | notice |
| Orders | `order_placed`, `order_status_changed` (old/new), `order_delivery_date_set`, `notification_recipients_changed` (added/removed) | notice |
| Designs | `design_saved`, `design_submitted` (lead info), `design_status_changed`, `design_note_added` (visibility, snippet), `design_deleted`, `design_milestones_updated`, `design_install_assistance_updated`, `design_managed_services_updated` | notice |
| Billing/Stripe | `invoices_generated` (month, count, total), `payment_recorded` (amount, method, ref), `stripe_checkout_created`, `stripe_webhook_received` (actor=system; signature failure → warning) | notice |
| Pricing/Catalog | `customer_discount_changed` (old/new pct), `deal_discount_applied`, `service_price_updated` (old/new), `bulk_price_update` (count, summary), `financing_terms_created`, `customer_commercial_changed`, `price_override_created`, `product_created`, `product_updated`, `component_created`, `component_updated`, `bundle_created`, `bundle_item_added` | notice |
| Integrations | `cdw_sync_triggered`, `papi_sync_triggered`, `excel_sync_triggered`, `bom_generated`, `topology_generated`, `designx_bom_suggested` | notice (failure → error) |
| Lifecycle/Onboarding | `subscription_status_changed`, `workflow_advanced`, `onboarding_updated` (fields_changed), `payment_method_validated` (type, last4 only) | notice |
| Security (central) | `zabbix_credentials_updated` (password never logged), `access_denied`, `rate_limit_exceeded` | warning (zabbix → notice) |
| System (central) | `server_error` (error_code, request_id) | error |

Common SD fields on every event: `request_id`, `tenant_id`, `user_id`, `actor_role`, `ip`, `ua`, `endpoint`, `status` — auto-filled from request context.

## 7. Rollout phases

1. **Foundations:** `logging_config` (formatter, severity map incl. the custom NOTICE level, redaction), `RequestContextMiddleware`, rsyslog config, `/var/log/secureoffice` provisioning, central hooks (403/429/5xx), `.gitignore` entry for `logs/` (the dev file sink writes `./logs/dev/` from day one). Also pin the Python version in `requirements.txt`/CI: the dev virtualenvs run 3.11.15 but nothing records that requirement, and the system fallback (`/usr/bin/python3` = 3.9.6) is past end-of-life — an unpinned prod install could silently land on it.
2. **Auth events** — the highest-value category.
3. **Business/admin events** — remaining catalog, service layer by service layer.
4. **Ops:** rotation cron (logrotate-backed), archive + repo symlink per §5.2, retention.
5. **Off-box durability — decision 2026-06-11: S3-archives-only for now.** The daily job syncs dated archives to S3 (`SECUREOFFICE_S3_BUCKET` env; `deploy/aws/` has the minimal List+Put IAM policy — no delete/read, so a compromised instance can't erase shipped audit history — and per-stream lifecycle rules). Live tail-based shipping (CloudWatch/Fluent Bit) is deferred until there's a search/alerting need. **Accepted residual risk:** up to 24h of the newest logs die with the instance.
6. **Later:** dashboards, alert-severity wiring (e.g., auth-failure thresholds → severity 1).

## 8. Open questions / risks

- **Searchability:** files have no query API — finding "everything user X did in May" means `zgrep` across archives, or SSH + `tail -f`/`grep` for live debugging. Fine pre-launch; for team-wide search without SSH, pick a log platform in phase 5 (config-only thanks to tail-based shipping, §5.5).
- **Archive location:** §5.2 adopts `/var/log/secureoffice/archive/` + repo symlink as the default — flag if plain repo-root `logs/` is a hard requirement.
- **EC2 durability:** resolved 2026-06-11 — S3 archive sync ships with phase 5 (set `SECUREOFFICE_S3_BUCKET` at deploy); live shipping deferred, leaving up to 24h of newest logs instance-local. Revisit if compliance needs tighter RPO.
- **Multi-worker ordering:** rsyslog interleaves lines from N uvicorn workers; lines are atomic but not strictly time-ordered across workers — timestamps are authoritative.
- **SD-ID enterprise number:** `audit@99999` is a placeholder — use Enidus's private enterprise number (or register one).
- **rsyslog rate limiting:** default burst limits (`$SystemLogRateLimitInterval`) can silently drop messages — must be disabled for local1 so audit events are never dropped.
- **Message size:** rsyslog's default `$MaxMessageSize` is 8KB — a `server_error` line carrying a long stack trace plus structured data can be silently truncated. Raise the limit in `deploy/rsyslog.d/secureoffice.conf` and cap traceback length in the formatter.
- **Disk:** `/var/log` partition needs usage monitoring; gzip in the daily job keeps archive growth manageable.
