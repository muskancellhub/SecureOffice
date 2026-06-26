import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TenantKey(Base):
    """Per-tenant Data Encryption Key, stored wrapped by the master KEK
    (docs/PII_ENCRYPTION.md §2, §6).

    The DB holds only the *wrapped* DEK — a database dump alone is useless
    without the KEK (which lives outside the DB). ``key_version`` travels with
    the wrapped DEK so the KEK/DEK can be rotated without guessing which key
    encrypted what.
    """

    __tablename__ = 'tenant_keys'

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        primary_key=True,
    )
    # v1:<b64 iv>:<b64 tag>:<b64 ciphertext> of the 32-byte DEK, wrapped with the KEK.
    wrapped_dek: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
