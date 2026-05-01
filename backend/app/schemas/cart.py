from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class AddCartLineRequest(BaseModel):
    # UUID validation at the schema boundary — malformed ids fail as 422, not 500.
    catalog_item_id: UUID
    quantity: int = Field(default=1, ge=1)
    applies_to_line_id: UUID | None = None


class UpdateCartLineRequest(BaseModel):
    quantity: int | None = Field(default=None, ge=1)
    catalog_item_id: UUID | None = None


class CartLineResponse(BaseModel):
    id: str
    catalog_item_id: str
    item_name: str
    item_type: str
    category: str | None
    billing_cycle: str | None
    quantity: int
    unit_price: float
    currency: str
    line_total: float
    applies_to_line_id: str | None
    applies_to_item_name: str | None
    created_at: datetime


class CartResponse(BaseModel):
    id: str
    status: str
    lines: list[CartLineResponse]
    one_time_subtotal: float
    monthly_subtotal: float
    estimated_12_month_total: float
    currency: str
