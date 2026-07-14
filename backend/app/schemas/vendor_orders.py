"""Vendor-facing order DTOs.

Deliberately trimmed vs. the buyer OrderDetailResponse: a vendor sees only the
lines they supply and each order's fulfillment status — NO pricing, margin,
totals, or buyer contact PII. The stripping is enforced server-side in
routes/vendor.py; these schemas simply have no field to carry that data.
"""
from datetime import date, datetime
from pydantic import BaseModel


class VendorOrderLineResponse(BaseModel):
    id: str
    name: str
    sku: str | None
    qty: int
    line_type: str
    component_type: str | None
    billing: str
    interval: str | None
    created_at: datetime


class VendorOrderSummaryResponse(BaseModel):
    id: str
    public_id: str
    status: str
    # Buyer organization name only — for fulfillment context, no contact PII.
    buyer_company: str | None = None
    estimated_delivery_date: date | None = None
    confirmed_delivery_date: date | None = None
    line_count: int
    total_qty: int
    created_at: datetime
    updated_at: datetime


class VendorOrderDetailResponse(VendorOrderSummaryResponse):
    lines: list[VendorOrderLineResponse]
