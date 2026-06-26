"""Low-level cryptographic primitives for per-tenant PII encryption.

Implements the envelope-encryption building blocks described in
``docs/PII_ENCRYPTION.md`` (§2–§3):

  * AES-256-GCM (AEAD) for both field values and DEK wrapping.
  * A versioned, self-describing stored format ``v1:<b64 iv>:<b64 tag>:<b64 ct>``.
  * ``tenant_id`` carried as AAD on every field encryption so ciphertext is
    cryptographically bound to its tenant — decrypting tenant A's value under
    tenant B's context throws.

This module is intentionally dependency-free beyond ``cryptography`` and the
standard library: it knows nothing about SQLAlchemy, tenants, or settings.
Higher layers (``key_provider``, ``encryption``) compose these primitives.
"""
from __future__ import annotations

import base64
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Format version prefix. Lets the backfill skip already-encrypted values and
# leaves room for an algorithm/format change later (§3 "Stored format").
FORMAT_VERSION = 'v1'

# 96-bit nonce is the AES-GCM standard/optimal size. A fresh one is drawn for
# every encrypt call — never reused with the same key (§3).
_IV_BYTES = 12
_KEY_BYTES = 32  # AES-256
_TAG_BYTES = 16  # GCM auth tag


class CryptoError(Exception):
    """Raised when decryption fails — wrong key, wrong tenant (AAD), tampering,
    or a malformed blob. Callers must treat this as a hard error and never fall
    back to returning the raw/garbage value (§7 read path)."""


def generate_dek() -> bytes:
    """A fresh random 32-byte Data Encryption Key (§3 'DEK generation')."""
    return secrets.token_bytes(_KEY_BYTES)


def is_encrypted(value: object) -> bool:
    """True if ``value`` is a string already in the ``v1:`` stored format.

    Used to keep both writes and the backfill idempotent — an already-encrypted
    value is never re-encrypted.
    """
    return isinstance(value, str) and value.startswith(FORMAT_VERSION + ':')


def _pack(iv: bytes, tag: bytes, ciphertext: bytes) -> str:
    """Render the three byte components as ``v1:<b64 iv>:<b64 tag>:<b64 ct>``."""
    b64 = lambda b: base64.b64encode(b).decode('ascii')
    return ':'.join((FORMAT_VERSION, b64(iv), b64(tag), b64(ciphertext)))


def _unpack(blob: str) -> tuple[bytes, bytes, bytes]:
    """Parse a ``v1:`` blob back into ``(iv, tag, ciphertext)``.

    Raises ``CryptoError`` on anything that isn't a well-formed v1 blob so a
    corrupt/truncated column never silently decrypts to garbage.
    """
    if not isinstance(blob, str):
        raise CryptoError('encrypted value is not a string')
    parts = blob.split(':')
    if len(parts) != 4 or parts[0] != FORMAT_VERSION:
        raise CryptoError('unrecognized encrypted value format')
    try:
        iv = base64.b64decode(parts[1])
        tag = base64.b64decode(parts[2])
        ciphertext = base64.b64decode(parts[3])
    except (ValueError, TypeError) as exc:
        raise CryptoError(f'invalid base64 in encrypted value: {exc}') from exc
    if len(iv) != _IV_BYTES or len(tag) != _TAG_BYTES:
        raise CryptoError('encrypted value has invalid iv/tag length')
    return iv, tag, ciphertext


def _encrypt(plaintext: bytes, key: bytes, aad: bytes | None) -> str:
    if len(key) != _KEY_BYTES:
        raise CryptoError('key must be 32 bytes (AES-256)')
    iv = secrets.token_bytes(_IV_BYTES)
    # AESGCM appends the 16-byte tag to the ciphertext; split it back out so the
    # stored format keeps iv/tag/ct as distinct, individually-versionable parts.
    ct_with_tag = AESGCM(key).encrypt(iv, plaintext, aad)
    ciphertext, tag = ct_with_tag[:-_TAG_BYTES], ct_with_tag[-_TAG_BYTES:]
    return _pack(iv, tag, ciphertext)


def _decrypt(blob: str, key: bytes, aad: bytes | None) -> bytes:
    if len(key) != _KEY_BYTES:
        raise CryptoError('key must be 32 bytes (AES-256)')
    iv, tag, ciphertext = _unpack(blob)
    try:
        return AESGCM(key).decrypt(iv, ciphertext + tag, aad)
    except InvalidTag as exc:
        # Wrong key, wrong tenant (AAD mismatch), or tampered ciphertext.
        raise CryptoError('decryption failed: authentication tag mismatch') from exc


# ── Field encryption (DEK + tenant_id AAD) ──────────────────────────────────

def encrypt_field(plaintext: str, dek: bytes, tenant_id: str) -> str:
    """Encrypt a PII field value with the tenant's DEK, binding it to the tenant
    via AAD. Returns the ``v1:`` stored blob."""
    return _encrypt(plaintext.encode('utf-8'), dek, str(tenant_id).encode('utf-8'))


def decrypt_field(blob: str, dek: bytes, tenant_id: str) -> str:
    """Inverse of :func:`encrypt_field`. The same ``tenant_id`` must be supplied
    as AAD or GCM verification fails (raising ``CryptoError``)."""
    return _decrypt(blob, dek, str(tenant_id).encode('utf-8')).decode('utf-8')


# ── DEK wrapping (KEK, no AAD) ──────────────────────────────────────────────

def wrap_dek(dek: bytes, kek: bytes) -> str:
    """Wrap (encrypt) a tenant DEK with the master KEK for storage in
    ``tenant_keys.wrapped_dek``. Returns the ``v1:`` stored blob."""
    return _encrypt(dek, kek, None)


def unwrap_dek(blob: str, kek: bytes) -> bytes:
    """Recover a raw DEK from its wrapped form using the master KEK."""
    return _decrypt(blob, kek, None)
