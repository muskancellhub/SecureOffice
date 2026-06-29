"""Per-tenant PII encryption service and ORM wiring.

This is the layer that ties the crypto primitives (``app.core.crypto``) and the
master-key provider (``app.core.key_provider``) to the application's data:

  * **Field registry** — the single, auditable source of truth listing exactly
    which ``(model, column)`` pairs are encrypted (docs/PII_ENCRYPTION.md §4).
  * **DEK cache** — an in-memory LRU + TTL cache of unwrapped per-tenant DEKs so
    the steady-state cost is pure AES, well under 1 ms (§9). On a miss the DEK is
    unwrapped from ``tenant_keys`` (and lazily provisioned if absent).
  * **Encrypt on write** — a single ``before_flush`` session listener encrypts
    every registered field on new/dirty instances, using the row's own
    ``tenant_id`` as AAD. Centralising the *write* direction is fail-safe: no
    individual call site can forget to encrypt and silently persist plaintext.
  * **Decrypt on read** — explicit ``decrypt_instance`` calls at the (few,
    enumerated) read boundaries. Decryption is explicit rather than a load-event
    so it runs *after* a query has materialised, never re-entrantly mid-result.

Mechanism note (vs docs/PII_ENCRYPTION.md §8): the plan sketched "explicit
encrypt/decrypt in the repos". Because ``tenant_id`` is a real column on every
encrypted table, the AAD is available directly from each instance — so the
plan's stated reason for avoiding transparent handling (having to thread the
tenant through a contextvar) does not apply. A central ``before_flush`` encrypt
hook is therefore both simpler and strictly safer for the security-critical
write path, while reads stay explicit. The crypto design itself is unchanged.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

from sqlalchemy import event, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.core import crypto
from app.core.crypto import CryptoError
from app.core.key_provider import get_key_provider

# ── Field registry (docs/PII_ENCRYPTION.md §4) ──────────────────────────────
# Maps ``__tablename__`` → tuple of encrypted column attribute names. Keyed by
# table name (a string) to avoid importing the model classes at module load and
# creating import cycles; the listener resolves an instance's table via its
# mapper. This is the authoritative list — adding a column here is all that is
# needed to bring it into encryption (plus a TEXT migration + backfill).
#
# Deliberately EXCLUDED from v1 (need a blind index for equality lookups — §4):
#   users.email, users.provider_id            (login / SSO keys, queried by ==)
#   payments.external_reference               (Square idempotency check filters
#                                              on it in square_webhook_handler)
ENCRYPTED_FIELDS: dict[str, tuple[str, ...]] = {
    'users': ('mobile', 'name'),
    'tenant_onboarding': ('admin_name', 'admin_email', 'admin_phone', 'tax_id', 'duns_number'),
    'vendors': ('federal_tax_id',),
    'assets': ('serial_number', 'location'),
}


class _DekCache:
    """Thread-safe LRU + TTL cache of unwrapped DEKs (raw 32-byte keys).

    Bounds memory (LRU) and the staleness window (TTL) so a rotated/revoked DEK
    is not used indefinitely. The cached value is the *unwrapped* key, so a hit
    avoids both the DB read and the KEK unwrap (§9).
    """

    def __init__(self, maxsize: int = 512, ttl_seconds: float = 600.0):
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._store: OrderedDict[str, tuple[float, bytes]] = OrderedDict()

    def get(self, tenant_id: str) -> bytes | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(tenant_id)
            if entry is None:
                return None
            expires_at, dek = entry
            if expires_at < now:
                self._store.pop(tenant_id, None)
                return None
            self._store.move_to_end(tenant_id)
            return dek

    def put(self, tenant_id: str, dek: bytes) -> None:
        with self._lock:
            self._store[tenant_id] = (time.monotonic() + self._ttl, dek)
            self._store.move_to_end(tenant_id)
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)

    def invalidate(self, tenant_id: str) -> None:
        with self._lock:
            self._store.pop(tenant_id, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class EncryptionService:
    """Resolves per-tenant DEKs and encrypts/decrypts instance fields.

    Stateless apart from the process-wide DEK cache and KEK provider, so it is
    cheap to construct per request/operation: ``EncryptionService(db)``.
    """

    # One cache for the whole process — DEKs are stable per tenant, so sharing
    # across requests is exactly what we want (and is what keeps KEK/DB work rare).
    _cache = _DekCache()

    def __init__(self, db: Session):
        self.db = db
        self._key_provider = get_key_provider()

    # ── DEK lifecycle ──────────────────────────────────────────────────────
    def _unwrap(self, wrapped_dek: str) -> bytes:
        return crypto.unwrap_dek(wrapped_dek, self._key_provider.get_kek())

    def get_dek(self, tenant_id) -> bytes:
        """Return the tenant's raw DEK, provisioning one on first use.

        Lookup order: in-memory cache → ``tenant_keys`` row (unwrap) → create.
        Lazy creation means every tenant-creation path (signup, vendor signup,
        seeds, tests) gets a DEK automatically the first time any of its PII is
        written — no per-path onboarding hook can be missed.
        """
        tid = str(tenant_id)
        cached = self._cache.get(tid)
        if cached is not None:
            return cached

        from app.models.tenant_key import TenantKey

        row = self.db.get(TenantKey, tenant_id if not isinstance(tenant_id, str) else _as_uuid(tenant_id))
        if row is not None:
            dek = self._unwrap(row.wrapped_dek)
            self._cache.put(tid, dek)
            return dek

        # No key yet for this tenant — generate, wrap, and persist within the
        # caller's transaction (added to the session; flushed with it).
        dek = crypto.generate_dek()
        wrapped = crypto.wrap_dek(dek, self._key_provider.get_kek())
        self.db.add(TenantKey(
            tenant_id=tenant_id if not isinstance(tenant_id, str) else _as_uuid(tenant_id),
            wrapped_dek=wrapped,
            key_version=1,
        ))
        self._cache.put(tid, dek)
        return dek

    def provision_tenant(self, tenant_id) -> None:
        """Eagerly ensure a tenant has a DEK (onboarding hook, §7). Idempotent —
        a no-op if one already exists. Encryption also provisions lazily, so this
        is an optimisation/explicitness aid, not a correctness requirement."""
        self.get_dek(tenant_id)

    # ── Per-instance encrypt / decrypt ─────────────────────────────────────
    def encrypt_instance(self, obj) -> None:
        """Encrypt every registered, not-yet-encrypted field on ``obj`` in place,
        using ``obj.tenant_id`` as AAD. Idempotent (skips ``v1:`` values and
        ``None``)."""
        fields = _fields_for(obj)
        if not fields:
            return
        tenant_id = _tenant_id_of(obj)
        if tenant_id is None:
            return
        dek = None
        for name in fields:
            value = getattr(obj, name, None)
            if value is None or crypto.is_encrypted(value):
                continue
            if dek is None:
                dek = self.get_dek(tenant_id)
            setattr(obj, name, crypto.encrypt_field(str(value), dek, str(tenant_id)))

    def decrypt_instance(self, obj) -> None:
        """Decrypt every registered, encrypted field on ``obj`` in place.

        Uses ``set_committed_value`` so the restored plaintext is treated as the
        loaded-from-DB value and does NOT mark the attribute dirty — a read must
        never schedule a spurious re-encrypting UPDATE. Plaintext values (mixed
        state during rollout / pre-backfill) are left untouched.
        """
        fields = _fields_for(obj)
        if not fields:
            return
        tenant_id = _tenant_id_of(obj)
        if tenant_id is None:
            return
        dek = None
        for name in fields:
            value = getattr(obj, name, None)
            if not crypto.is_encrypted(value):
                continue
            if dek is None:
                dek = self.get_dek(tenant_id)
            set_committed_value(obj, name, crypto.decrypt_field(value, dek, str(tenant_id)))

    def decrypt_all(self, objs) -> None:
        for obj in objs:
            if obj is not None:
                self.decrypt_instance(obj)


# ── Module helpers ──────────────────────────────────────────────────────────

def _as_uuid(value: str):
    import uuid
    return uuid.UUID(value)


def _fields_for(obj) -> tuple[str, ...]:
    table = getattr(type(obj), '__tablename__', None)
    return ENCRYPTED_FIELDS.get(table, ()) if table else ()


def _tenant_id_of(obj):
    """The row's tenant id (the AAD). ``None`` if unset — e.g. a half-built
    instance — in which case encryption is skipped and retried on the next flush
    once the FK is populated."""
    return getattr(obj, 'tenant_id', None)


def has_encrypted_fields(obj) -> bool:
    return bool(_fields_for(obj))


# ── Central encrypt-on-write listener ───────────────────────────────────────

def _encrypt_pending(session: Session) -> None:
    """Encrypt registered fields on every new/dirty instance about to be flushed.

    Runs inside ``before_flush`` so any object added by ``get_dek`` (a newly
    provisioned ``tenant_keys`` row) is naturally included in the same flush.
    """
    targets = [obj for obj in session.new if has_encrypted_fields(obj)]
    targets += [obj for obj in session.dirty if has_encrypted_fields(obj)]
    if not targets:
        return
    svc = EncryptionService(session)
    for obj in targets:
        svc.encrypt_instance(obj)


@event.listens_for(Session, 'before_flush')
def _before_flush_encrypt(session: Session, flush_context, instances) -> None:
    _encrypt_pending(session)


def invalidate_dek_cache(tenant_id: str | None = None) -> None:
    """Drop cached DEK(s) — call after a key rotation (§11) or in tests."""
    if tenant_id is None:
        EncryptionService._cache.clear()
    else:
        EncryptionService._cache.invalidate(str(tenant_id))


__all__ = [
    'EncryptionService',
    'ENCRYPTED_FIELDS',
    'CryptoError',
    'invalidate_dek_cache',
    'has_encrypted_fields',
]
