from datetime import datetime
from pydantic import BaseModel, Field
from app.models.catalog import BillingCycle, CatalogItemType


class CatalogItemResponse(BaseModel):
    id: str
    type: CatalogItemType
    name: str
    sku: str
    vendor: str | None
    vendor_sku: str | None
    description: str | None
    price: float
    currency: str
    billing_cycle: BillingCycle
    is_active: bool
    availability: str | None
    attributes: dict
    managed_service_price: float | None = None
    created_at: datetime

    # Unified catalog fields.
    category: str | None = None
    product_type: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    pricing_basis: str | None = None
    model: str | None = None
    notes: str | None = None
    raw_source: dict | None = None


class CatalogSyncResponse(BaseModel):
    synced_count: int
    created_count: int
    updated_count: int
    errors: list[str] = Field(default_factory=list)
    items: list[CatalogItemResponse]


class UpdateManagedServiceRequest(BaseModel):
    price: float | None = None
    is_active: bool | None = None
    features: list[str] | None = None


class UpdateDeviceManagedServicePriceRequest(BaseModel):
    managed_service_price: float | None = None


class BulkUpdateManagedServicePricesRequest(BaseModel):
    updates: list[dict] = Field(default_factory=list)
