from datetime import date, datetime
from pydantic import BaseModel, Field
from app.models.lifecycle import PaymentMethod, PaymentStatus


class BillingMonthPointResponse(BaseModel):
    month: str
    one_time_total: float
    recurring_total: float
    total: float


class BillingTotalsResponse(BaseModel):
    one_time_last_12_months: float
    recurring_last_12_months: float
    projected_next_12_months: float
    current_monthly_recurring: float


class BillingOverviewResponse(BaseModel):
    past_months: list[BillingMonthPointResponse]
    projected_months: list[BillingMonthPointResponse]
    totals: BillingTotalsResponse


class PaymentResponse(BaseModel):
    id: str
    tenant_id: str
    invoice_id: str
    amount: float
    currency: str
    status: PaymentStatus
    method: PaymentMethod
    external_reference: str | None
    paid_at: datetime
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class InvoiceResponse(BaseModel):
    id: str
    tenant_id: str
    subscription_id: str | None
    billing_month: date
    amount: float
    currency: str
    status: str
    due_date: date
    issued_at: datetime
    paid_at: datetime | None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    payments: list[PaymentResponse] = Field(default_factory=list)


class RunInvoicingRequest(BaseModel):
    billing_month: date | None = None


class RecordPaymentRequest(BaseModel):
    amount: float | None = None
    method: PaymentMethod = PaymentMethod.MANUAL
    external_reference: str | None = None
