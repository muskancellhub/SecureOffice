from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


DesignStatus = Literal[
    'draft',
    'reviewed',
    'submitted',
    'in_review',
    'bom_finalized',
    'proposal_ready',
    'approved',
    'order_decomposed',
    'fulfillment_in_progress',
    'installation_scheduled',
    'installed',
    'completed',
]
DesignNoteVisibility = Literal['internal', 'customer']
InstallMode = Literal['self_install', 'remote_assistance', 'onsite_visit']


class DesignMilestonesInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    estimated_review_date: str | None = Field(default=None, alias='estimatedReviewDate')
    estimated_proposal_date: str | None = Field(default=None, alias='estimatedProposalDate')
    estimated_fulfillment_date: str | None = Field(default=None, alias='estimatedFulfillmentDate')
    estimated_installation_date: str | None = Field(default=None, alias='estimatedInstallationDate')
    confirmed_fulfillment_date: str | None = Field(default=None, alias='confirmedFulfillmentDate')
    confirmed_installation_date: str | None = Field(default=None, alias='confirmedInstallationDate')


class DesignInstallAssistanceInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    install_mode: InstallMode | None = Field(default=None, alias='installMode')
    preferred_install_date: str | None = Field(default=None, alias='preferredInstallDate')
    install_notes: str | None = Field(default=None, max_length=5000, alias='installNotes')


class DesignUpdateInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    visibility: DesignNoteVisibility = 'internal'
    message: str = Field(min_length=1, max_length=5000)


class LeadCaptureInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    full_name: str = Field(min_length=1, max_length=255, alias='fullName')
    email: EmailStr
    company_name: str = Field(min_length=1, max_length=255, alias='companyName')
    phone: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=5000)


class LeadCapturePatchInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    full_name: str | None = Field(default=None, min_length=1, max_length=255, alias='fullName')
    email: EmailStr | None = None
    company_name: str | None = Field(default=None, min_length=1, max_length=255, alias='companyName')
    phone: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=5000)


class SaveNetworkDesignRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    design_id: str | None = Field(default=None, alias='designId')
    design_name: str | None = Field(default=None, alias='designName')
    calculator_input: dict[str, Any] | None = Field(default=None, alias='calculatorInput')
    calculator_result: dict[str, Any] | None = Field(default=None, alias='calculatorResult')
    bom: dict[str, Any] | None = None
    topology: dict[str, Any] | None = None
    drawio_xml: str | None = Field(default=None, alias='drawioXml')
    assumptions: list[str] = Field(default_factory=list)
    lead: LeadCapturePatchInput | None = None
    submit: bool = False
    status: DesignStatus | None = None
    session_key: str | None = Field(default=None, alias='sessionKey')
    milestones: DesignMilestonesInput | None = None
    install_assistance: DesignInstallAssistanceInput | None = Field(default=None, alias='installAssistance')
    metadata: dict[str, Any] | None = None


class SubmitNetworkDesignRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lead: LeadCaptureInput


class UpdateNetworkDesignStatusRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: DesignStatus
    note: str | None = Field(default=None, max_length=5000)
    note_visibility: DesignNoteVisibility = Field(default='internal', alias='noteVisibility')


class UpdateNetworkDesignMilestonesRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    milestones: DesignMilestonesInput


class UpdateNetworkDesignInstallationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    install_assistance: DesignInstallAssistanceInput = Field(alias='installAssistance')


class AddNetworkDesignUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    update: DesignUpdateInput


class DesignLeadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    full_name: str = Field(alias='fullName')
    email: str
    company_name: str = Field(alias='companyName')
    phone: str | None = None
    notes: str | None = None
    created_at: datetime = Field(alias='createdAt')
    updated_at: datetime = Field(alias='updatedAt')


class DesignStatusHistoryEntryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: DesignStatus
    changed_at: str = Field(alias='changedAt')
    changed_by: str | None = Field(default=None, alias='changedBy')
    note: str | None = None


class DesignUpdateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    request_id: str = Field(alias='requestId')
    created_at: str = Field(alias='createdAt')
    author: str | None = None
    visibility: DesignNoteVisibility
    message: str


class DesignMilestonesResponse(DesignMilestonesInput):
    pass


class DesignInstallAssistanceResponse(DesignInstallAssistanceInput):
    pass


class NetworkDesignSummaryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    quote_id: str | None = Field(default=None, alias='quoteId')
    order_id: str | None = Field(default=None, alias='orderId')
    workflow_instance_id: str | None = Field(default=None, alias='workflowInstanceId')
    design_name: str | None = Field(default=None, alias='designName')
    status: DesignStatus
    status_updated_at: datetime | None = Field(default=None, alias='statusUpdatedAt')
    estimated_capex: float = Field(alias='estimatedCapex')
    ap_count: int = Field(alias='apCount')
    switch_count: int = Field(alias='switchCount')
    submitted_at: datetime | None = Field(default=None, alias='submittedAt')
    milestones: DesignMilestonesResponse = Field(default_factory=DesignMilestonesResponse)
    latest_update: str | None = Field(default=None, alias='latestUpdate')
    next_milestone: str | None = Field(default=None, alias='nextMilestone')
    created_at: datetime = Field(alias='createdAt')
    updated_at: datetime = Field(alias='updatedAt')
    lead: DesignLeadResponse | None = None


class ManagedServicesConfigRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled_categories: list[str] = Field(default_factory=list, alias='enabledCategories')
    excluded_item_ids: list[str] = Field(default_factory=list, alias='excludedItemIds')


class ManagedServiceDeviceEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item_id: str = Field(alias='itemId')
    name: str
    sku: str
    category: str | None = None
    quantity: int
    managed_service_price: float = Field(alias='managedServicePrice')
    excluded: bool = False


class ManagedServiceCategorySummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    group: str
    group_label: str = Field(alias='groupLabel')
    enabled: bool
    device_count: int = Field(alias='deviceCount')
    excluded_count: int = Field(alias='excludedCount')
    applied_count: int = Field(alias='appliedCount')
    monthly_total: float = Field(alias='monthlyTotal')
    devices: list[ManagedServiceDeviceEntry] = Field(default_factory=list)


class ManagedServicesDesignResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    config: dict[str, Any] = Field(default_factory=dict)
    categories: list[ManagedServiceCategorySummary] = Field(default_factory=list)
    grand_total_monthly: float = Field(alias='grandTotalMonthly')


class NetworkDesignDetailResponse(NetworkDesignSummaryResponse):
    calculator_input: dict[str, Any] = Field(default_factory=dict, alias='calculatorInput')
    calculator_result: dict[str, Any] = Field(default_factory=dict, alias='calculatorResult')
    bom: dict[str, Any] = Field(default_factory=dict)
    topology: dict[str, Any] = Field(default_factory=dict)
    drawio_xml: str | None = Field(default=None, alias='drawioXml')
    assumptions: list[str] = Field(default_factory=list)
    status_history: list[DesignStatusHistoryEntryResponse] = Field(default_factory=list, alias='statusHistory')
    updates: list[DesignUpdateResponse] = Field(default_factory=list)
    install_assistance: DesignInstallAssistanceResponse = Field(
        default_factory=DesignInstallAssistanceResponse, alias='installAssistance'
    )
    decomposition: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    managed_services: dict[str, Any] = Field(default_factory=dict, alias='managedServices')
    metadata: dict[str, Any] = Field(default_factory=dict)
