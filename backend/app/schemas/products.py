"""Schemas for the Phase 4 admin catalog APIs."""
from datetime import datetime

from pydantic import BaseModel, Field


# ── components ──────────────────────────────────────────────────────────────
class ComponentResponse(BaseModel):
    id: str
    product_id: str
    component_type: str
    financial_model: str
    label: str
    vendor_component_sku: str | None = None
    vendor_cost: float
    msrp: float | None = None
    uom: str
    billing: str
    interval: str | None = None
    margin_pct: float | None = None
    leasing_pct: float | None = None
    default_qty: int
    is_required: bool
    is_active: bool
    attributes: dict


class CreateComponentRequest(BaseModel):
    component_type: str
    financial_model: str = 'BOTH'
    label: str
    vendor_component_sku: str | None = None
    vendor_cost: float
    msrp: float | None = None
    uom: str = 'PER_DEVICE'
    billing: str = 'ONE_TIME'
    interval: str | None = None
    margin_pct: float | None = None
    leasing_pct: float | None = None
    default_qty: int = 1
    is_required: bool = True
    is_active: bool = True
    attributes: dict = Field(default_factory=dict)


class UpdateComponentRequest(BaseModel):
    component_type: str | None = None
    financial_model: str | None = None
    label: str | None = None
    vendor_component_sku: str | None = None
    vendor_cost: float | None = None
    msrp: float | None = None
    uom: str | None = None
    billing: str | None = None
    interval: str | None = None
    margin_pct: float | None = None
    leasing_pct: float | None = None
    default_qty: int | None = None
    is_required: bool | None = None
    is_active: bool | None = None
    attributes: dict | None = None


# ── products ────────────────────────────────────────────────────────────────
class ProductResponse(BaseModel):
    id: str
    vendor: str
    technology: str
    sku: str
    vendor_sku: str | None = None
    name: str
    description: str | None = None
    default_financial_model: str
    margin_pct: float | None = None
    leasing_pct: float | None = None
    is_active: bool
    attributes: dict
    components: list[ComponentResponse] = Field(default_factory=list)


class CreateProductRequest(BaseModel):
    vendor: str
    technology: str
    sku: str
    name: str
    vendor_sku: str | None = None
    description: str | None = None
    default_financial_model: str = 'BOTH'
    margin_pct: float | None = None
    leasing_pct: float | None = None
    is_active: bool = True
    attributes: dict = Field(default_factory=dict)


class CreateProductWithComponentsRequest(CreateProductRequest):
    # BUG-PRODUCT-DATA-004: product + all components submitted together so the
    # backend can persist them in ONE transaction (no orphaned product if a
    # component is invalid). At least one component is required.
    components: list[CreateComponentRequest] = Field(min_length=1)


class UpdateProductRequest(BaseModel):
    vendor: str | None = None
    technology: str | None = None
    name: str | None = None
    vendor_sku: str | None = None
    description: str | None = None
    default_financial_model: str | None = None
    margin_pct: float | None = None
    leasing_pct: float | None = None
    is_active: bool | None = None
    attributes: dict | None = None


# ── financing terms ─────────────────────────────────────────────────────────
class FinancingTermsResponse(BaseModel):
    id: str
    name: str
    term_months: int
    annual_rate_pct: float
    subscription_interval: str
    is_default: bool
    is_active: bool


class CreateFinancingTermsRequest(BaseModel):
    name: str
    term_months: int = 36
    annual_rate_pct: float = 0.05
    subscription_interval: str = Field(default='MONTH', pattern='^(MONTH|YEAR)$')
    is_default: bool = False
    is_active: bool = True


# ── customer commercial config ──────────────────────────────────────────────
class UpdateCommercialRequest(BaseModel):
    default_margin_pct: float | None = Field(default=None, ge=0.0, le=0.95)
    opex_eligible: bool | None = None
    credit_status: str | None = Field(default=None, pattern='^(PENDING|PASS|FAIL)$')
    credit_limit: float | None = None


class CommercialResponse(BaseModel):
    tenant_id: str
    default_discount_pct: float
    # None = tenant hasn't customized → inherits the 25% global default (Phase 7 D2).
    default_margin_pct: float | None = None
    opex_eligible: bool
    credit_status: str
    credit_limit: float | None = None
    updated_at: datetime


class PriceOverrideRequest(BaseModel):
    product_id: str | None = None
    component_id: str | None = None
    override_margin_pct: float | None = None
    override_unit_price: float | None = None


class PriceOverrideResponse(BaseModel):
    id: str
    tenant_id: str
    product_id: str | None = None
    component_id: str | None = None
    override_margin_pct: float | None = None
    override_unit_price: float | None = None


# ── bundles (Phase 5) ────────────────────────────────────────────────────────
class BundleItemResponse(BaseModel):
    id: str
    bundle_id: str
    product_id: str
    default_qty: int
    is_optional: bool
    is_removable: bool
    sort_order: int


class BundleResponse(BaseModel):
    id: str
    sku: str
    name: str
    vendor: str | None = None
    technology: str | None = None
    description: str | None = None
    is_active: bool
    attributes: dict
    items: list[BundleItemResponse] = Field(default_factory=list)


class CreateBundleRequest(BaseModel):
    sku: str
    name: str
    vendor: str | None = None
    technology: str | None = None
    description: str | None = None
    is_active: bool = True
    attributes: dict = Field(default_factory=dict)


class AddBundleItemRequest(BaseModel):
    product_id: str
    default_qty: int = 1
    is_optional: bool = False
    is_removable: bool = True
    sort_order: int = 0
