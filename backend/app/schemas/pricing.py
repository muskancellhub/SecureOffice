from datetime import datetime
from pydantic import BaseModel, Field


class CustomerPricingResponse(BaseModel):
    tenant_id: str
    default_discount_pct: float
    updated_at: datetime


class UpdateCustomerPricingRequest(BaseModel):
    default_discount_pct: float = Field(ge=0.0, le=0.95)


class DealPricingResponse(BaseModel):
    quote_id: str
    incremental_discount_pct: float
    updated_at: datetime


class UpdateDealPricingRequest(BaseModel):
    incremental_discount_pct: float = Field(ge=0.0, le=0.95)


class ComponentPreviewRequest(BaseModel):
    """Phase 2 component-pricing preview (no persistence)."""

    product_id: str
    financial_model: str = Field(default='CAPEX', pattern='^(CAPEX|OPEX)$')
    interval: str = Field(default='MONTH', pattern='^(MONTH|YEAR)$')
    # {component_id: qty} — optional components to include; also overrides required qty.
    selections: dict[str, int] = Field(default_factory=dict)


class StandaloneComponentPreviewRequest(BaseModel):
    """Phase 7 D10 — price one component à-la-carte."""

    component_id: str
    qty: int = Field(default=1, ge=1)
    financial_model: str = Field(default='CAPEX', pattern='^(CAPEX|OPEX)$')
    interval: str = Field(default='MONTH', pattern='^(MONTH|YEAR)$')
