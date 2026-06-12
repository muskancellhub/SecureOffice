import enum
import uuid
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class CartStatus(str, enum.Enum):
    ACTIVE = 'ACTIVE'
    CHECKED_OUT = 'CHECKED_OUT'


class Cart(Base):
    __tablename__ = 'carts'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False)
    status: Mapped[CartStatus] = mapped_column(Enum(CartStatus, name='cart_status'), nullable=False, default=CartStatus.ACTIVE)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    lines = relationship('CartLine', back_populates='cart', cascade='all, delete-orphan')


class CartLine(Base):
    """One priced component line (Phase 7 — component model only).

    A configured product lands as a parent line (its DEVICE / primary
    component) plus child lines linked via ``applies_to_line_id``. A standalone
    à-la-carte component (D10) is a single line with no parent.
    ``catalog_item_id`` is a retired legacy snapshot column (no FK — the
    catalog_items table is gone); it stays NULL on every new line.
    """

    __tablename__ = 'cart_lines'
    __table_args__ = (
        # Exactly one source: legacy snapshot rows carry catalog_item_id,
        # component-model rows carry component_id (+ product_id).
        CheckConstraint(
            '(catalog_item_id IS NOT NULL)::int + (component_id IS NOT NULL)::int = 1',
            name='cart_lines_one_source_check',
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('carts.id', ondelete='CASCADE'), nullable=False)
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('products.id', ondelete='RESTRICT'), nullable=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('product_components.id', ondelete='RESTRICT'), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='USD')
    price_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    applies_to_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('cart_lines.id', ondelete='SET NULL'), nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    cart = relationship('Cart', back_populates='lines')
    product = relationship('Product')
    component = relationship('ProductComponent')
    applies_to_line = relationship('CartLine', remote_side='CartLine.id')
