from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.catalog import BillingCycle, CatalogItemType


class SyncRoutersRequest(BaseModel):
    query: str = 'business routers with sku, brand, model, ports, wifi standard, price and availability'
    limit: int = 20


class SyncNetworkVendorCatalogRequest(BaseModel):
    file_path: str | None = None


class IntegrationSyncLogResponse(BaseModel):
    integration_name: str
    scope: str
    status: str
    synced_count: int
    created_count: int
    updated_count: int
    error_excerpt: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


class SyncPapiDevicesRequest(BaseModel):
    page_size: int = 100
    max_pages: int = 20
    eip: bool = True
    classic: bool = True


class DesignXSuggestBOMRequest(BaseModel):
    requirement: str = Field(min_length=2, max_length=2000)
    employee_count: int = Field(default=10, ge=1, le=100000)
    site_count: int = Field(default=1, ge=1, le=10000)
    existing_customer: bool = False


class DesignXSuggestedLineResponse(BaseModel):
    catalog_item_id: str
    type: CatalogItemType
    category: str | None
    name: str
    sku: str
    vendor: str | None
    quantity: int
    unit_price: float
    currency: str
    billing_cycle: BillingCycle
    reason: str
    source: str = 'DESIGNX'
    confidence: float


class DesignXSuggestBOMResponse(BaseModel):
    summary: str
    suggestions: list[DesignXSuggestedLineResponse]
    unavailable_categories: list[str]


class NetworkBomPreferencesInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    preferred_vendor: str | None = Field(default=None, alias='preferredVendor')
    cable_type: Literal['CAT5', 'CAT6', 'CAT6e'] | None = Field(default=None, alias='cableType')
    include_ups: bool | None = Field(default=None, alias='includeUPS')
    include_licenses: bool | None = Field(default=None, alias='includeLicenses')
    include_installation: bool | None = Field(default=None, alias='includeInstallation')
    include_managed_services: bool | None = Field(default=None, alias='includeManagedServices')
    switch_port_preference: int | None = Field(default=None, ge=1, le=256, alias='switchPortPreference')
    tax_pct: float | None = Field(default=None, ge=0.0, le=100.0, alias='taxPct')


class GenerateNetworkBomRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    calculator_result: dict = Field(alias='calculatorResult')
    business_context: dict | None = Field(default=None, alias='businessContext')
    preferences: NetworkBomPreferencesInput = Field(default_factory=NetworkBomPreferencesInput)


class NetworkBomLineResponse(BaseModel):
    line_id: str
    item_id: str | None
    sku: str | None
    source_type: str
    name: str
    vendor: str | None
    category: str | None
    quantity: int
    unit_price: float
    line_total: float
    selection_reason: str
    connectivity: Literal['wired', 'wireless', 'sim'] | None = None
    cable_type: Literal['CAT5', 'CAT6', 'CAT6e'] | None = None
    cable_length_meters: float | None = None
    price_per_meter: float | None = None
    wired_drop_count: int | None = None
    office_area_sqft: float | None = None
    cost_share_pct: float | None = None
    is_derived_bom: bool | None = None


class GenerateNetworkBomResponse(BaseModel):
    line_items: list[NetworkBomLineResponse]
    subtotal: float
    tax: float
    grand_total: float
    summary: str
    assumptions: list[str]
