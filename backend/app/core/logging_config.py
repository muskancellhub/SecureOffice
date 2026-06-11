"""Central logging setup: RFC 5424 formatting, severity mapping, redaction.

Design: docs/LOGGING_PLAN.md. Two streams over one pipeline:
  - root / "secureoffice.*"  → facility local0 (application logs)
  - "secureoffice.audit"     → facility local1 (audit events)

Everything here is identical across environments except the handler picked in
configure_logging() (LOG_SINK env var, plan §4.5): 'file' writes RFC 5424
lines directly (dev), 'syslog' sends to rsyslog via /dev/log (prod).
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import socket
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

APP_NAME = 'secureoffice2'

# Syslog facilities (RFC 5424 §6.2.1): local0 = app logs, local1 = audit.
FACILITY_APP = logging.handlers.SysLogHandler.LOG_LOCAL0
FACILITY_AUDIT = logging.handlers.SysLogHandler.LOG_LOCAL1

# SD-IDs for the STRUCTURED-DATA element. 99999 is a placeholder private
# enterprise number (plan §8) — swap once a real PEN is registered.
SD_ID_AUDIT = 'audit@99999'
SD_ID_REQUEST = 'request@99999'

AUDIT_LOGGER_NAME = 'secureoffice.audit'
ACCESS_LOGGER_NAME = 'secureoffice.access'

# Python logging has no NOTICE level (INFO=20 jumps to WARNING=30), but
# notice (5) is the default severity for successful audit events (plan §2.2).
NOTICE = 25

# Stack traces are appended to the MSG field on one line; cap so a deep trace
# can't blow past rsyslog's message size limit (plan §8).
_MAX_TRACEBACK_CHARS = 4000

# Keys whose values must never reach a log file, matched case-insensitively
# as substrings of the field name (plan §4.2).
REDACTED_KEY_PARTS = (
    'password', 'passwd', 'token', 'secret', 'api_key', 'apikey',
    'otp', 'card_number', 'cardnumber', 'authorization', 'cvv',
    'private_key', 'client_secret', 'credential',
)

_HOSTNAME = socket.gethostname() or '-'


def _syslog_severity(levelno: int) -> int:
    if levelno >= logging.CRITICAL:
        return 2
    if levelno >= logging.ERROR:
        return 3
    if levelno >= logging.WARNING:
        return 4
    if levelno >= NOTICE:
        return 5
    if levelno >= logging.INFO:
        return 6
    return 7


def _is_redacted_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in REDACTED_KEY_PARTS)


def redact(value: Any) -> Any:
    """Recursively replace values of credential-looking keys with [REDACTED]."""
    if isinstance(value, dict):
        return {
            k: '[REDACTED]' if _is_redacted_key(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v) for v in value)
    return value


def _sanitize(text: str) -> str:
    """Strip newlines/control chars so user-controlled strings can't forge
    log lines (plan §4.2, log-injection hygiene)."""
    return ''.join(c if (c >= ' ' or c == '\t') else ' ' for c in text)


def _escape_sd_value(value: Any) -> str:
    # RFC 5424 §6.3.3: escape backslash, double-quote, and closing bracket.
    text = _sanitize(str(value))
    return text.replace('\\', '\\\\').replace('"', '\\"').replace(']', '\\]')


class RedactionFilter(logging.Filter):
    """Applies the redaction denylist to structured data before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        sd = getattr(record, 'sd', None)
        if isinstance(sd, dict):
            record.sd = redact(sd)
        return True


class RFC5424Formatter(logging.Formatter):
    """Formats records as RFC 5424 lines.

    <PRI>1 TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG

    include_pri=True for the file sink (we write the whole line); False for
    SysLogHandler, which computes and prepends <PRI> itself — including it
    here would double-encode it (plan §3 gotchas).
    """

    def __init__(self, facility: int, include_pri: bool):
        super().__init__()
        self.facility = facility
        self.include_pri = include_pri

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
            timespec='microseconds'
        ).replace('+00:00', 'Z')

        msgid = _sanitize(str(getattr(record, 'msgid', '') or '-')).replace(' ', '_') or '-'

        sd = getattr(record, 'sd', None)
        if isinstance(sd, dict) and sd:
            sd_text = ''.join(
                '[{} {}]'.format(
                    sd_id,
                    ' '.join(f'{k}="{_escape_sd_value(v)}"' for k, v in fields.items()),
                )
                for sd_id, fields in sd.items()
                if isinstance(fields, dict)
            ) or '-'
        else:
            sd_text = '-'

        msg = _sanitize(record.getMessage())
        if record.exc_info:
            trace = ''.join(traceback.format_exception(*record.exc_info))
            msg = f'{msg} | {_sanitize(trace)[:_MAX_TRACEBACK_CHARS]}'

        line = f'1 {ts} {_HOSTNAME} {APP_NAME} {record.process} {msgid} {sd_text} {msg}'
        if self.include_pri:
            pri = self.facility * 8 + _syslog_severity(record.levelno)
            return f'<{pri}>{line}'
        return line


def _file_handler(log_dir: str, filename: str, facility: int) -> logging.Handler:
    os.makedirs(log_dir, exist_ok=True)
    handler = logging.handlers.WatchedFileHandler(os.path.join(log_dir, filename), encoding='utf-8')
    handler.setFormatter(RFC5424Formatter(facility=facility, include_pri=True))
    return handler


def _syslog_handler(facility: int, address: str) -> logging.Handler:
    handler = logging.handlers.SysLogHandler(address=address, facility=facility)
    # SysLogHandler maps levelname → syslog priority; teach it our custom level.
    handler.priority_map = {**handler.priority_map, 'NOTICE': 'notice'}
    handler.setFormatter(RFC5424Formatter(facility=facility, include_pri=False))
    return handler


def configure_logging(
    app_env: str = 'development',
    log_sink: str = 'file',
    log_dir: str = './logs/dev',
    log_level: str = '',
    syslog_address: str = '/dev/log',
) -> None:
    """Set up the two-stream pipeline. Safe to call more than once (tests)."""
    logging.addLevelName(NOTICE, 'NOTICE')

    level_name = (log_level or ('INFO' if app_env == 'production' else 'DEBUG')).upper()
    level = logging.getLevelName(level_name)
    if not isinstance(level, int):
        level = logging.INFO

    redaction = RedactionFilter()

    if log_sink == 'syslog':
        app_handler = _syslog_handler(FACILITY_APP, syslog_address)
        audit_handler = _syslog_handler(FACILITY_AUDIT, syslog_address)
    else:
        app_handler = _file_handler(log_dir, 'app.log', FACILITY_APP)
        audit_handler = _file_handler(log_dir, 'audit.log', FACILITY_AUDIT)
    app_handler.addFilter(redaction)
    audit_handler.addFilter(redaction)

    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(app_handler)

    # Dev convenience: mirror app logs to the console in human-readable form.
    if app_env != 'production' and log_sink == 'file':
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        console.addFilter(redaction)
        root.addHandler(console)

    # Audit stream: own handler (local1), never propagates into app logs, and
    # never suppressed by LOG_LEVEL — audited admin reads are info-level.
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.setLevel(logging.INFO)
    for h in list(audit_logger.handlers):
        audit_logger.removeHandler(h)
    audit_logger.addHandler(audit_handler)
    audit_logger.propagate = False

    # Uvicorn: drop its default access line (the RequestContextMiddleware
    # access log carries request_id instead); route its error log through us.
    uvicorn_access = logging.getLogger('uvicorn.access')
    uvicorn_access.handlers = []
    uvicorn_access.propagate = False
    for name in ('uvicorn', 'uvicorn.error'):
        ul = logging.getLogger(name)
        ul.handlers = []
        ul.propagate = True
