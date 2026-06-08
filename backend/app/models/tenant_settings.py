"""Per-tenant soft settings (multi-tenant Phase 3).

JSONB-per-tenant for things that don't warrant typed columns: design-ops queue
prefs, managed-service category availability, and feature flags. Money/pricing/
financing stay in typed tables (Phases 0–1) — keep them out of here.
"""
import uuid

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TenantSettings(Base):
    __tablename__ = 'tenant_settings'

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), primary_key=True,
    )
    design_ops: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"),
    )
    admin_services: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"),
    )
    feature_flags: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"),
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
