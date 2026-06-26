"""Backfill: encrypt existing plaintext PII in place (docs/PII_ENCRYPTION.md §10).

For every tenant, ensures a DEK exists and rewrites each registered PII column
from plaintext to the ``v1:iv:tag:ciphertext`` blob. Run AFTER the column-widening
migration (which ``apply_runtime_migrations`` performs on startup).

Properties:
  * **Idempotent** — values already in ``v1:`` form are skipped, so running it
    twice (or after new tenants onboard) is safe and only touches plaintext rows.
  * **Per-tenant transaction** — each tenant commits independently; a failure on
    one tenant doesn't roll back already-migrated tenants.
  * Uses the same ``EncryptionService.encrypt_instance`` path as live writes (in
    fact, marking a row dirty and committing would also encrypt it via the
    before_flush listener — we call encrypt explicitly for clarity and so a
    --dry-run can report intended changes without writing).

Usage:
    python -m scripts.backfill_pii_encryption [--dry-run]
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

import app.models  # noqa: F401 — registers models + the before_flush listener
from app.core.crypto import is_encrypted
from app.core.database import SessionLocal
from app.core.encryption import ENCRYPTED_FIELDS, EncryptionService
from app.models.tenant import Tenant

# Resolve the model class for each encrypted table from the registry, so this
# script and the live encryption path can never drift on which columns/tables
# are in scope.
from app.models.user import User
from app.models.onboarding import TenantOnboarding
from app.models.vendor import Vendor
from app.models.lifecycle import Asset

_TABLE_MODELS = {
    'users': User,
    'tenant_onboarding': TenantOnboarding,
    'vendors': Vendor,
    'assets': Asset,
}


def _count_plaintext(obj, fields: tuple[str, ...]) -> int:
    n = 0
    for name in fields:
        value = getattr(obj, name, None)
        if value is not None and not is_encrypted(value):
            n += 1
    return n


def backfill_tenant(db, enc: EncryptionService, tenant_id, *, dry_run: bool) -> dict[str, int]:
    """Encrypt every plaintext PII value for one tenant. Returns per-table counts
    of values that were (or, in dry-run, would be) encrypted."""
    counts: dict[str, int] = {}
    # Make sure the tenant has a DEK before touching any row.
    if not dry_run:
        enc.provision_tenant(tenant_id)

    for table, fields in ENCRYPTED_FIELDS.items():
        model = _TABLE_MODELS[table]
        rows = db.scalars(select(model).where(model.tenant_id == tenant_id)).all()
        changed = 0
        for row in rows:
            pending = _count_plaintext(row, fields)
            if pending == 0:
                continue
            changed += pending
            if not dry_run:
                enc.encrypt_instance(row)
        if changed:
            counts[table] = changed
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Encrypt existing plaintext PII columns per tenant.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report how many values would be encrypted without writing.')
    args = parser.parse_args(argv)

    grand_total = 0
    with SessionLocal() as db:
        tenant_ids = list(db.scalars(select(Tenant.id)).all())
        enc = EncryptionService(db)
        print(f'Backfilling PII encryption for {len(tenant_ids)} tenant(s)'
              + (' [DRY RUN]' if args.dry_run else '') + ' ...')
        for tid in tenant_ids:
            try:
                counts = backfill_tenant(db, enc, tid, dry_run=args.dry_run)
                if args.dry_run:
                    db.rollback()
                else:
                    db.commit()
            except Exception as exc:  # isolate per-tenant failures
                db.rollback()
                print(f'  tenant {tid}: ERROR — {exc}', file=sys.stderr)
                continue
            total = sum(counts.values())
            grand_total += total
            if total:
                detail = ', '.join(f'{k}={v}' for k, v in sorted(counts.items()))
                print(f'  tenant {tid}: {total} value(s) [{detail}]')
    verb = 'would encrypt' if args.dry_run else 'encrypted'
    print(f'Done. {verb} {grand_total} plaintext PII value(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
