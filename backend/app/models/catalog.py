import enum
import uuid
from sqlalchemy import Boolean, DateTime, Enum, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class CatalogItemType(str, enum.Enum):
    DEVICE = 'DEVICE'
    SERVICE = 'SERVICE'


class BillingCycle(str, enum.Enum):
    ONE_TIME = 'ONE_TIME'
    MONTHLY = 'MONTHLY'
    YEARLY = 'YEARLY'


class CatalogItem(Base):
    __tablename__ = 'catalog_items'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[CatalogItemType] = mapped_column(Enum(CatalogItemType, name='catalog_item_type'), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='USD')
    billing_cycle: Mapped[BillingCycle] = mapped_column(
        Enum(BillingCycle, name='billing_cycle'), nullable=False, default=BillingCycle.ONE_TIME
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    availability: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
