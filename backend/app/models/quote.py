import enum
import uuid
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from app.core.database import Base


class QuoteStatus(str, enum.Enum):
    DRAFT = 'DRAFT'
    SENT = 'SENT'
    ACCEPTED = 'ACCEPTED'
    CONVERTED = 'CONVERTED'
    EXPIRED = 'EXPIRED'


class QuoteLineType(str, enum.Enum):
    DEVICE = 'DEVICE'
    SERVICE = 'SERVICE'


class BillingType(str, enum.Enum):
    ONE_TIME = 'ONE_TIME'
    RECURRING = 'RECURRING'


class BillingInterval(str, enum.Enum):
    MONTH = 'MONTH'
    YEAR = 'YEAR'


class Quote(Base):
    __tablename__ = 'quotes'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        'created_by',
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )
    public_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        server_default=text("'QID' || lpad(nextval('quote_public_id_seq'::regclass)::text, 4, '0')"),
    )
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus, name='quote_status_v2', native_enum=False),
        nullable=False,
        default=QuoteStatus.DRAFT,
    )
    one_time_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    monthly_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    projected_12_month_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='USD')
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Backward-compatible attribute alias for existing service/repository code.
    created_by = synonym('created_by_user_id')

    lines = relationship('QuoteLine', back_populates='quote', cascade='all, delete-orphan')
    deal_pricing = relationship('DealPricing', back_populates='quote', uselist=False, cascade='all, delete-orphan')


class QuoteLine(Base):
    __tablename__ = 'quote_lines'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('quotes.id', ondelete='CASCADE'), nullable=False)
    line_type: Mapped[QuoteLineType] = mapped_column(
        Enum(QuoteLineType, name='quote_line_type_v1', native_enum=False),
        nullable=False,
    )
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('catalog_items.id', ondelete='SET NULL'),
        nullable=True,
    )
    name_snapshot: Mapped[str] = mapped_column('name', String(255), nullable=False)
    sku_snapshot: Mapped[str | None] = mapped_column('sku', String(128), nullable=True)
    vendor_snapshot: Mapped[str | None] = mapped_column('vendor', String(128), nullable=True, default='CDW')
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    list_price_snapshot: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    final_unit_price_snapshot: Mapped[float] = mapped_column('unit_price', Numeric(12, 2), nullable=False)
    billing_type: Mapped[BillingType] = mapped_column(
        'billing',
        Enum(BillingType, name='quote_billing_type_v1', native_enum=False),
        nullable=False,
    )
    interval: Mapped[BillingInterval | None] = mapped_column(
        Enum(BillingInterval, name='quote_billing_interval_v1', native_enum=False),
        nullable=True,
    )
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    parent_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('quote_lines.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Backward-compatible aliases for existing frontend serializers.
    name = synonym('name_snapshot')
    sku = synonym('sku_snapshot')
    vendor = synonym('vendor_snapshot')
    unit_price = synonym('final_unit_price_snapshot')
    billing = synonym('billing_type')

    quote = relationship('Quote', back_populates='lines')
    parent_line = relationship('QuoteLine', remote_side='QuoteLine.id')
