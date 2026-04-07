import enum
import uuid
from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from app.core.database import Base
from app.models.quote import BillingInterval, BillingType, QuoteLineType


class OrderStatus(str, enum.Enum):
    SUBMITTED = 'SUBMITTED'
    PROCESSING = 'PROCESSING'
    VENDOR_ORDERED = 'VENDOR_ORDERED'
    SHIPPED = 'SHIPPED'
    DELIVERED = 'DELIVERED'
    ACTIVE = 'ACTIVE'


class Order(Base):
    __tablename__ = 'orders'

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
        server_default=text("'OID' || lpad(nextval('order_public_id_seq'::regclass)::text, 4, '0')"),
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('quotes.id', ondelete='SET NULL'),
        nullable=True,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name='order_status_v1', native_enum=False),
        nullable=False,
        default=OrderStatus.SUBMITTED,
    )
    estimated_delivery_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    confirmed_delivery_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Backward-compatible attribute alias for existing service/repository code.
    created_by = synonym('created_by_user_id')

    lines = relationship('OrderLine', back_populates='order', cascade='all, delete-orphan')
    quote = relationship('Quote')


class OrderLine(Base):
    __tablename__ = 'order_lines'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    line_type: Mapped[QuoteLineType] = mapped_column(
        Enum(QuoteLineType, name='order_line_type_v1', native_enum=False),
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
        Enum(BillingType, name='order_billing_type_v1', native_enum=False),
        nullable=False,
    )
    interval: Mapped[BillingInterval | None] = mapped_column(
        Enum(BillingInterval, name='order_billing_interval_v1', native_enum=False),
        nullable=True,
    )
    metadata_json: Mapped[dict] = mapped_column('metadata', JSONB, nullable=False, default=dict)
    parent_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('order_lines.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Backward-compatible aliases for existing frontend serializers.
    name = synonym('name_snapshot')
    sku = synonym('sku_snapshot')
    vendor = synonym('vendor_snapshot')
    unit_price = synonym('final_unit_price_snapshot')
    billing = synonym('billing_type')

    order = relationship('Order', back_populates='lines')
    parent_line = relationship('OrderLine', remote_side='OrderLine.id')
