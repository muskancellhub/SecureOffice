from datetime import date, datetime
from pydantic import BaseModel, Field
from app.models.lifecycle import SubscriptionStatus, WorkflowStatus, WorkflowStepStatus


class ContractResponse(BaseModel):
    id: str
    tenant_id: str
    order_id: str
    created_by: str
    status: str
    term_months: int
    sla_tier: str
    entitlements: dict = Field(default_factory=dict)
    start_date: date
    end_date: date | None
    created_at: datetime
    updated_at: datetime


class SubscriptionResponse(BaseModel):
    id: str
    tenant_id: str
    contract_id: str
    order_line_id: str | None
    name: str
    sku: str | None
    vendor: str | None
    qty: int
    unit_price: float
    currency: str
    interval: str
    status: str
    start_date: date
    end_date: date | None
    next_billing_date: date | None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class UpdateSubscriptionStatusRequest(BaseModel):
    status: SubscriptionStatus


class AssetResponse(BaseModel):
    id: str
    tenant_id: str
    contract_id: str | None
    order_line_id: str | None
    name: str
    sku: str | None
    vendor: str | None
    asset_type: str
    status: str
    owner_user_id: str | None
    location: str | None
    serial_number: str | None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class WorkflowStepResponse(BaseModel):
    id: str
    workflow_instance_id: str
    stage_key: str
    display_name: str
    sequence: int
    status: WorkflowStepStatus
    retries: int
    started_at: datetime | None
    completed_at: datetime | None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class WorkflowInstanceResponse(BaseModel):
    id: str
    tenant_id: str
    order_id: str
    template_key: str
    status: WorkflowStatus
    current_stage: str
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepResponse]
