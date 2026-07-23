"""Reap abandoned unverified accounts (BUG-AUTH-011).

A signup persists the user as ``is_verified=False`` before the OTP step. If the
user abandons ``/verify-otp`` the row lingers and blocks that email from ever
signing up again. This job deletes such accounts once they are older than the
TTL (``UNVERIFIED_ACCOUNT_TTL_MINUTES``), along with any tenant left empty.

The same reap runs lazily inside ``AuthService.signup`` for a single email, so
this script is the belt-and-suspenders scheduled sweep (run it from cron).

Usage:
    python -m scripts.reap_unverified_accounts [--older-than-minutes N]
"""
from __future__ import annotations

import argparse
import sys

import app.models  # noqa: F401 — registers models + listeners
from app.core.database import SessionLocal
from app.services.auth_service import AuthService


def main() -> int:
    parser = argparse.ArgumentParser(description='Reap abandoned unverified accounts.')
    parser.add_argument(
        '--older-than-minutes', type=int, default=None,
        help='Override the TTL; defaults to settings.unverified_account_ttl_minutes.',
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        purged = AuthService(db).purge_stale_unverified(older_than_minutes=args.older_than_minutes)
    print(f'Reaped {purged} unverified account(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
