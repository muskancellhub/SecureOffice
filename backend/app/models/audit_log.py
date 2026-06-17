"""Append-only audit-event table (BUG-AUD-001).

The audit subsystem primarily writes RFC 5424 syslog (docs/LOGGING_PLAN.md).
This table is the queryable, immutable mirror: a DbAuditHandler dual-writes
each event here, PostgreSQL triggers block UPDATE/DELETE (runtime_migrations),
and GET /audit-logs exposes it. The file/syslog SIEM pipeline is unchanged.
"""

import uuid

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # user_id / tenant_id are stored as the audit pipeline emits them (UUID
    # strings, or NULL for the RFC 5424 nil '-'); kept as text to avoid FKs that
    # could block writes or fail on system-path events.
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ua: Mapped[str | None] = mapped_column(String(512), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='success')
    # 'metadata' is reserved on the declarative Base, so map the column under a
    # different Python attribute name.
    audit_metadata: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
