import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# Phase 7: the legacy discount-off-list model (list_prices) is retired —
# every live price comes from ComponentPricingService (cost × (1 + markup)).


class CustomerPricing(Base):
    __tablename__ = 'customer_pricing'

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        primary_key=True,
    )
    default_discount_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.30)
    # Tenant-wide markup (Phase 7 D2). NULL = not customized → inherit the 25%
    # global default in ComponentPricingService, so "unset" ≠ a real 0.
    default_margin_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True, default=None)
    credit_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default='PENDING', server_default='PENDING'
    )
    credit_limit: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    opex_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text('FALSE')
    )
    credit_checked_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credit_bureau_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DealPricing(Base):
    __tablename__ = 'deal_pricing'

    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('quotes.id', ondelete='CASCADE'),
        primary_key=True,
    )
    incremental_discount_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.0)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    quote = relationship('Quote', back_populates='deal_pricing', lazy='joined')
