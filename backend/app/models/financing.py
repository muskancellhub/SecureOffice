"""OPEX lease configuration (Secure Office pricing engine, Phase 1).

Drives the OPEX amortizing annuity: term_months + annual_rate_pct. The default
36-mo / 5% row reproduces the manager's worked example ($19.78 lease MRC on a
$660 financed principal). See docs/plans/phase-1-schema-and-seed.md.
"""
import uuid

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class FinancingTerms(Base):
    __tablename__ = 'financing_terms'

    # Per-tenant (multi-tenant Phase 1): each tenant owns its financing config;
    # existing global rows were backfilled to the CellHub master tenant.
    __table_args__ = (
        UniqueConstraint('tenant_id', 'name', name='uq_financing_tenant_name'),
        # At most one default term per tenant.
        Index('uq_financing_tenant_default', 'tenant_id', unique=True, postgresql_where=text('is_default')),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False, default=36)
    annual_rate_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.0500)
    subscription_interval: Mapped[str] = mapped_column(String(16), nullable=False, default='MONTH')
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
