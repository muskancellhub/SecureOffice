from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

ValidationStatus = Literal['PENDING', 'VERIFIED', 'FAILED']
PaymentMethodType = Literal['CARD', 'BANK_TRANSFER', 'MANUAL']


class OnboardingProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str
    organization_name: str | None
    admin_name: str | None
    admin_email: str | None
    admin_phone: str | None
    credit_validation_status: ValidationStatus
    tax_validation_status: ValidationStatus
    duns_number: str | None
    tax_id: str | None
    company_setup_completed: bool
    payment_method_setup: bool
    payment_validation_status: ValidationStatus
    payment_method_type: str | None
    payment_method_last4: str | None
    onboarding_completed: bool
    metadata: dict = Field(default_factory=dict)
    missing_requirements: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UpdateOnboardingProfileRequest(BaseModel):
    organization_name: str | None = None
    admin_name: str | None = None
    admin_email: EmailStr | None = None
    admin_phone: str | None = None
    credit_validation_status: ValidationStatus | None = None
    tax_validation_status: ValidationStatus | None = None
    duns_number: str | None = None
    tax_id: str | None = None
    company_setup_completed: bool | None = None
    payment_method_setup: bool | None = None
    metadata: dict | None = None


class ValidatePaymentMethodRequest(BaseModel):
    payment_method_type: PaymentMethodType
    last4: str | None = None
    external_reference: str | None = None
