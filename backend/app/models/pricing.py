import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ListPrice(Base):
    __tablename__ = 'list_prices'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'catalog_item_id', 'vendor', name='uq_list_prices_tenant_item_vendor'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    catalog_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('catalog_items.id', ondelete='CASCADE'), nullable=False
    )
    vendor: Mapped[str] = mapped_column(String(128), nullable=False, default='CDW')
    list_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='USD')
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CustomerPricing(Base):
    __tablename__ = 'customer_pricing'

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        primary_key=True,
    )
    default_discount_pct: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False, default=0.30)
    # Cost-plus-margin model (spec §4.5) — coexists with the legacy discount model above.
    default_margin_pct: Mapped[float] = mapped_column(
        Numeric(6, 4), nullable=False, default=0.20, server_default='0.2000'
    )
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
