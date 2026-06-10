import re
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from app.schemas.auth import validate_email

ValidationStatus = Literal['PENDING', 'VERIFIED', 'FAILED']
PaymentMethodType = Literal['CARD', 'BANK_TRANSFER', 'MANUAL']

# US states + DC + territories — addresses are US-only for now (jurisdiction is
# NY/NJ per the EULA). Used to validate the `state` field.
US_STATES = frozenset({
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL',
    'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT',
    'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI',
    'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI', 'GU', 'AS', 'MP',
})
_ZIP_RE = re.compile(r'^\d{5}(-\d{4})?$')


class AddressInput(BaseModel):
    """A US business address. All fields are optional so a blank address means
    'not provided yet' (onboarding stays incomplete), but the moment ANY field
    is filled the core fields become required and are format-checked — i.e. you
    can't save a half-typed address."""
    line1: str | None = Field(default=None, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=2)
    postal_code: str | None = Field(default=None, max_length=10)
    country: str = Field(default='US', max_length=2)

    @field_validator('line1', 'line2', 'city', 'state', 'postal_code', 'country', mode='before')
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode='after')
    def _validate(self):
        filled = any([self.line1, self.line2, self.city, self.state, self.postal_code])
        if not filled:
            return self  # blank address — allowed, treated as "not set"
        missing = [f for f in ('line1', 'city', 'state', 'postal_code') if not getattr(self, f)]
        if missing:
            labels = {'line1': 'street address', 'city': 'city', 'state': 'state', 'postal_code': 'ZIP code'}
            raise ValueError('Address is incomplete — please provide: ' + ', '.join(labels[f] for f in missing))
        state = (self.state or '').upper()
        if state not in US_STATES:
            raise ValueError('State must be a valid 2-letter US state code (e.g. NY, NJ, CA)')
        self.state = state
        if not _ZIP_RE.match(self.postal_code or ''):
            raise ValueError('ZIP code must be 5 digits or ZIP+4 (e.g. 07030 or 07030-1234)')
        self.country = (self.country or 'US').upper()
        return self


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
    operations_address: dict = Field(default_factory=dict)
    billing_address: dict = Field(default_factory=dict)
    billing_same_as_operations: bool = True
    metadata: dict = Field(default_factory=dict)
    missing_requirements: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class UpdateOnboardingProfileRequest(BaseModel):
    organization_name: str | None = None
    admin_name: str | None = None
    admin_email: EmailStr | None = None
    admin_phone: str | None = None

    @field_validator('admin_email')
    @classmethod
    def check_email(cls, v: str | None) -> str | None:
        return validate_email(v) if v else v
    credit_validation_status: ValidationStatus | None = None
    tax_validation_status: ValidationStatus | None = None
    duns_number: str | None = None
    tax_id: str | None = None
    company_setup_completed: bool | None = None
    payment_method_setup: bool | None = None
    operations_address: AddressInput | None = None
    billing_address: AddressInput | None = None
    billing_same_as_operations: bool | None = None
    metadata: dict | None = None


class ValidatePaymentMethodRequest(BaseModel):
    payment_method_type: PaymentMethodType
    last4: str | None = None
    external_reference: str | None = None
