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
