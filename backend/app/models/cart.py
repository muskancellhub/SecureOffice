import enum
import uuid
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
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
    __tablename__ = 'cart_lines'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cart_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('carts.id', ondelete='CASCADE'), nullable=False)
    catalog_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('catalog_items.id', ondelete='RESTRICT'), nullable=False
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
    catalog_item = relationship('CatalogItem')
    applies_to_line = relationship('CartLine', remote_side='CartLine.id')
