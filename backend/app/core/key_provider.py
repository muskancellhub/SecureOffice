"""Master-key (KEK) provider abstraction (docs/PII_ENCRYPTION.md §5, §8).

The KEK is accessed only through this small interface so that Phase 2 can swap
the v1 ``EnvKeyProvider`` (master key in an env var) for a ``KmsKeyProvider`` /
``KeyVaultKeyProvider`` (master key in a managed service) without touching any
other code. Everything above this layer asks for ``get_kek()`` and never cares
where the bytes come from.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.config import get_settings


class KeyProvider(ABC):
    """Returns the 32-byte master Key Encryption Key used to wrap/unwrap DEKs."""

    @abstractmethod
    def get_kek(self) -> bytes:  # pragma: no cover - interface
        ...


class EnvKeyProvider(KeyProvider):
    """v1 provider: reads ``MASTER_ENCRYPTION_KEY`` from settings (env/.env).

    Validation (present + base64 + exactly 32 bytes) lives in
    ``Settings.master_encryption_key_bytes`` so startup and this provider share a
    single fail-fast code path.
    """

    def get_kek(self) -> bytes:
        return get_settings().master_encryption_key_bytes()


def get_key_provider() -> KeyProvider:
    """Factory for the active provider. v1 always returns the env provider;
    Phase 2 selects KMS/Key Vault here based on config."""
    return EnvKeyProvider()
