from datetime import date, datetime
from pydantic import BaseModel, Field


class OrderLineResponse(BaseModel):
    id: str
    order_id: str
    line_type: str
    catalog_item_id: str | None
    name: str
    sku: str | None
    vendor: str | None
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


class OrderSummaryResponse(BaseModel):
    id: str
    public_id: str
    tenant_id: str
    created_by_user_id: str
    created_by: str
    quote_id: str | None
    quote_public_id: str | None = None
    status: str
    estimated_delivery_date: date | None = None
    confirmed_delivery_date: date | None = None
    created_at: datetime
    updated_at: datetime


class OrderDetailResponse(OrderSummaryResponse):
    lines: list[OrderLineResponse]


class UpdateOrderRequest(BaseModel):
    status: str | None = None
    estimated_delivery_date: date | None = None
    confirmed_delivery_date: date | None = None
