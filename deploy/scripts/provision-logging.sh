#!/usr/bin/env bash
# One-shot logging provisioning for a SecureOffice2 Linux host (EC2 user-data
# or manual). Idempotent — safe to re-run. See docs/LOGGING_PLAN.md §5, §5.5.
#
# Installs:
#   - /var/log/secureoffice/ (+archive/) with rsyslog-only write access
#   - rsyslog routing for local0 (app) / local1 (audit)
#   - logrotate config + daily root cron for rotation/archival/retention
#   - <repo>/logs symlink -> /var/log/secureoffice/archive (plan §5.2)
#
# Usage: sudo deploy/scripts/provision-logging.sh [repo_root]
#   repo_root defaults to the checkout containing this script.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Must run as root (sudo)." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="${1:-$(dirname "$DEPLOY_DIR")}"

echo "== SecureOffice2 logging provisioning (repo: $REPO_ROOT) =="

# 1. Live log directory: rsyslog writes, app has no write access (plan §5.1).
install -d -o syslog -g adm -m 0750 /var/log/secureoffice
install -d -o root   -g adm -m 0750 /var/log/secureoffice/archive
install -d -o root   -g root -m 0755 /var/lib/secureoffice

# 2. rsyslog routing (local0 -> app.log, local1 -> audit.log).
install -o root -g root -m 0644 "$DEPLOY_DIR/rsyslog.d/secureoffice.conf" \
    /etc/rsyslog.d/30-secureoffice.conf
systemctl restart rsyslog

# 3. Rotation: logrotate config + wrapper script + daily cron entry.
install -o root -g root -m 0644 "$DEPLOY_DIR/logrotate.d/secureoffice" \
    /etc/logrotate.d/secureoffice
install -o root -g root -m 0755 "$DEPLOY_DIR/scripts/secureoffice-rotate-logs" \
    /usr/local/bin/secureoffice-rotate-logs
install -o root -g root -m 0644 "$DEPLOY_DIR/cron.d/secureoffice-logs" \
    /etc/cron.d/secureoffice-logs

# 4. Repo-visible archives without tying log survival to the deploy dir
#    (plan §5.2): <repo>/logs is a symlink, never a real directory in prod.
if [[ -e "$REPO_ROOT/logs" && ! -L "$REPO_ROOT/logs" ]]; then
    echo "WARNING: $REPO_ROOT/logs exists and is not a symlink — leaving it alone." >&2
else
    ln -sfn /var/log/secureoffice/archive "$REPO_ROOT/logs"
fi

# 5. Smoke test: emit one line per facility and confirm rsyslog routed it.
logger -p local0.info  -t secureoffice2 "provisioning smoke test (app stream)"
logger -p local1.notice -t secureoffice2 "provisioning smoke test (audit stream)"
sleep 1
for f in app.log audit.log; do
    if grep -q 'provisioning smoke test' "/var/log/secureoffice/$f"; then
        echo "OK: /var/log/secureoffice/$f receiving"
    else
        echo "ERROR: /var/log/secureoffice/$f did not receive the smoke-test line" >&2
        exit 1
    fi
done

echo "== Done. App env should set LOG_SINK=syslog. Rotation runs daily at 00:05. =="
