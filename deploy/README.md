# deploy/ — server provisioning artifacts

Ops config for the SecureOffice2 logging pipeline (design: [docs/LOGGING_PLAN.md](../docs/LOGGING_PLAN.md)).
Nothing here runs in dev — on a dev machine the app writes RFC 5424 lines
directly to `./logs/dev/` (`LOG_SINK=file`, the default).

| Path | Installed at | Purpose |
|---|---|---|
| `rsyslog.d/secureoffice.conf` | `/etc/rsyslog.d/30-secureoffice.conf` | Route local0 (app) / local1 (audit) to `/var/log/secureoffice/*.log`; disable rate limiting for audit; 64k message size |
| `logrotate.d/secureoffice` | `/etc/logrotate.d/secureoffice` | Daily rename + gzip + HUP rsyslog |
| `scripts/secureoffice-rotate-logs` | `/usr/local/bin/secureoffice-rotate-logs` | Wrapper: logrotate → verify gzip → dated archive folders → retention (90d app / 365d audit) |
| `cron.d/secureoffice-logs` | `/etc/cron.d/secureoffice-logs` | Runs the wrapper daily at 00:05 as root |
| `scripts/provision-logging.sh` | run once via sudo / EC2 user-data | Installs all of the above, creates dirs + `<repo>/logs` symlink, smoke-tests both streams |
| `aws/iam-policy-log-archive.json` | EC2 instance role | Minimal List+Put for the archive sync — no delete/read, so the box can't erase shipped audit history |
| `aws/s3-lifecycle.json` | log-archive bucket | Glacier at 90d for both streams; app expires at 400d, audit never |

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
