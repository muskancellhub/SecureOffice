from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class RequirementsInput(BaseModel):
    business_type: Literal['office', 'restaurant', 'retail']
    num_users: int = Field(ge=1, le=100000)
    num_sites: int = Field(ge=1, le=10000)
    need_wifi6: bool = False
    need_dual_wan: bool = False
    budget_range: str = Field(min_length=1, max_length=128)


class DraftServiceInput(BaseModel):
    catalog_item_id: str
    qty: int | None = Field(default=None, ge=1, le=100000)
    pricing_basis: Literal['PER_DEVICE', 'PER_SITE'] | None = None


class DraftRouterInput(BaseModel):
    catalog_item_id: str
    qty: int = Field(default=1, ge=1, le=10000)
    attached_services: list[DraftServiceInput] = Field(default_factory=list)


class DraftSolutionInput(BaseModel):
    requirements: RequirementsInput
    routers: list[DraftRouterInput] = Field(default_factory=list)
    currency: str = Field(default='USD', min_length=3, max_length=8)


class CreateQuoteRequest(BaseModel):
    draft_solution: DraftSolutionInput | None = None


class PreviewQuoteRequest(BaseModel):
    draft_solution: DraftSolutionInput


class QuoteLineResponse(BaseModel):
    id: str
    quote_id: str
    line_type: str
    catalog_item_id: str | None
    name_snapshot: str
    sku_snapshot: str | None
    vendor_snapshot: str | None
    qty: int
    list_price_snapshot: float
    final_unit_price_snapshot: float
    unit_price: float
    billing_type: str
    billing: str
    interval: str | None
    metadata: dict = Field(default_factory=dict)
    parent_line_id: str | None
    created_at: datetime


class QuoteSummaryResponse(BaseModel):
    id: str
    public_id: str
    tenant_id: str
    created_by_user_id: str
    created_by: str
    status: str
    one_time_total: float
    monthly_total: float
    projected_12_month_cost: float
    currency: str
    default_discount_pct: float
    incremental_discount_pct: float
    created_at: datetime
    updated_at: datetime


class QuoteDetailResponse(QuoteSummaryResponse):
    lines: list[QuoteLineResponse]


class QuoteIdResponse(BaseModel):
    quote_id: str
    quote_public_id: str | None = None


class QuotePricingPreviewResponse(BaseModel):
    one_time_total: float
    monthly_total: float
    projected_12_month_cost: float
    currency: str
    default_discount_pct: float
    incremental_discount_pct: float
