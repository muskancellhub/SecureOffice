"""Component-driven catalog model (Secure Office pricing engine, Phase 1).

`products` (SKU header) -> `product_components` (priced Component Type rows) ->
`bundles`/`bundle_items` (reusable solutions). New MIX products live here; the
legacy `catalog_items` table stays intact (a component may link to a real
hardware record via `catalog_item_id`). See docs/plans/phase-1-schema-and-seed.md.

Enums use ``native_enum=False`` (stored as VARCHAR + CHECK) to match the
convention in quote.py/order.py and avoid CREATE TYPE ordering issues with the
startup sequence (apply_runtime_migrations runs before create_all).
"""
import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class ComponentType(str, enum.Enum):
    DEVICE = 'DEVICE'
    CLOUD_CONTROLLER = 'CLOUD_CONTROLLER'
    LINE_CHARGE = 'LINE_CHARGE'
    MANAGED_SERVICE = 'MANAGED_SERVICE'
    SIM = 'SIM'
    BACKUP_SIM = 'BACKUP_SIM'
    INSTALLATION = 'INSTALLATION'
    PROFESSIONAL_SERVICES = 'PROFESSIONAL_SERVICES'
    MAINTENANCE = 'MAINTENANCE'
    LICENSE = 'LICENSE'
    ACCESSORY = 'ACCESSORY'


class FinancialModel(str, enum.Enum):
    CAPEX = 'CAPEX'
    OPEX = 'OPEX'
    BOTH = 'BOTH'


class ComponentUom(str, enum.Enum):
    PER_DEVICE = 'PER_DEVICE'
    PER_LINE = 'PER_LINE'
    PER_SEAT = 'PER_SEAT'
    PER_HOUR = 'PER_HOUR'
    ONE_TIME = 'ONE_TIME'
    PER_DID = 'PER_DID'


class Product(Base):
    """SKU header — the manager's Vendor -> Technology -> SKU hierarchy."""

    __tablename__ = 'products'
    __table_args__ = (
        Index('idx_products_vendor_tech', 'vendor', 'technology'),
        Index('idx_products_vendor_tenant', 'vendor_tenant_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor: Mapped[str] = mapped_column(String(128), nullable=False)
    # Durable, id-based link to the supplier's VENDOR tenant. The `vendor` string
    # above stays as the catalog/display label; this FK is what vendor-scoped
    # order queries key off (nullable — not every product maps to an onboarded
    # vendor tenant). SET NULL so deleting a vendor tenant doesn't cascade the SKU.
    vendor_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='SET NULL'), nullable=True
    )
    technology: Mapped[str] = mapped_column(String(128), nullable=False)
    sku: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    vendor_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    default_financial_model: Mapped[FinancialModel] = mapped_column(
        Enum(FinancialModel, name='financial_model', native_enum=False),
        nullable=False,
        default=FinancialModel.BOTH,
    )
    margin_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    leasing_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    components = relationship('ProductComponent', back_populates='product', cascade='all, delete-orphan')


class ProductComponent(Base):
    """A priced Component Type row. Replaces hardcoded per-SKU price columns."""

    __tablename__ = 'product_components'
    __table_args__ = (
        CheckConstraint("billing IN ('ONE_TIME','RECURRING')", name='pc_billing_check'),
        CheckConstraint("interval IS NULL OR interval IN ('MONTH','YEAR')", name='pc_interval_check'),
        Index('idx_product_components_product', 'product_id'),
        Index('idx_product_components_type', 'component_type'),
        # A product carries one row per (component_type, vendor_component_sku) — keeps the seed idempotent.
        UniqueConstraint('product_id', 'component_type', 'vendor_component_sku', name='uq_pc_product_type_sku'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('products.id', ondelete='CASCADE'), nullable=False
    )
    component_type: Mapped[ComponentType] = mapped_column(
        Enum(ComponentType, name='component_type', native_enum=False), nullable=False
    )
    financial_model: Mapped[FinancialModel] = mapped_column(
        Enum(FinancialModel, name='financial_model', native_enum=False),
        nullable=False,
        default=FinancialModel.BOTH,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_component_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor_cost: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    msrp: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    uom: Mapped[ComponentUom] = mapped_column(
        Enum(ComponentUom, name='component_uom', native_enum=False),
        nullable=False,
        default=ComponentUom.PER_DEVICE,
    )
    billing: Mapped[str] = mapped_column(String(16), nullable=False, default='ONE_TIME')
    interval: Mapped[str | None] = mapped_column(String(16), nullable=True)
    margin_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    leasing_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    default_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    product = relationship('Product', back_populates='components')


class Bundle(Base):
    """A named reusable solution = group of products (Phase 5 assembles these)."""

    __tablename__ = 'bundles'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    technology: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    items = relationship('BundleItem', back_populates='bundle', cascade='all, delete-orphan')


class BundleItem(Base):
    __tablename__ = 'bundle_items'
    __table_args__ = (
        UniqueConstraint('bundle_id', 'product_id', name='uq_bundle_items_bundle_product'),
        Index('idx_bundle_items_bundle', 'bundle_id'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bundle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('bundles.id', ondelete='CASCADE'), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('products.id', ondelete='RESTRICT'), nullable=False
    )
    default_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_removable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    bundle = relationship('Bundle', back_populates='items')
    product = relationship('Product')


class CustomerPriceOverride(Base):
    """Per-customer price overrides (manager's "Pricing Overrides", spec §4.5)."""

    __tablename__ = 'customer_price_overrides'
    __table_args__ = (
        CheckConstraint(
            'product_id IS NOT NULL OR component_id IS NOT NULL', name='cpo_target_check'
        ),
        Index(
            'uq_cpo_tenant_component', 'tenant_id', 'component_id',
            unique=True, postgresql_where=text('component_id IS NOT NULL'),
        ),
        Index(
            'uq_cpo_tenant_product', 'tenant_id', 'product_id',
            unique=True, postgresql_where=text('product_id IS NOT NULL'),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('products.id', ondelete='CASCADE'), nullable=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('product_components.id', ondelete='CASCADE'), nullable=True
    )
    override_margin_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    override_unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
