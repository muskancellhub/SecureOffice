import re
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.models.user import UserRole, UserType

_PHONE_RE = re.compile(r'^\+?[\d\s\-().]{7,20}$')
_EMAIL_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


def validate_email(v: str) -> str:
    if not _EMAIL_RE.match(v):
        raise ValueError('Please enter a valid email address')
    return v


def validate_phone(v: str | None) -> str | None:
    if v is None:
        return v
    v = v.strip()
    if not v:
        return None
    if not _PHONE_RE.match(v) or not any(c.isdigit() for c in v):
        raise ValueError('Enter a valid phone number, e.g. +1 (555) 123-4567')
    return v


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    mobile: str | None = Field(default=None)
    name: str = Field(min_length=1, max_length=255)
    tenant_id: str | None = None

    @field_validator('email')
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email(v)

    @field_validator('name', mode='before')
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator('mobile')
    @classmethod
    def check_mobile(cls, v: str | None) -> str | None:
        return validate_phone(v)


class VendorSignupRequest(BaseModel):
    contact_name: str = Field(min_length=1, max_length=255)
    contact_email: EmailStr
    contact_phone: str | None = Field(default=None)
    password: str = Field(min_length=6, max_length=128)
    company_name: str = Field(min_length=1, max_length=255)
    address_street: str = Field(min_length=1, max_length=500)
    address_city: str = Field(min_length=1, max_length=255)
    address_state: str = Field(min_length=1, max_length=100)
    address_zip: str = Field(min_length=1, max_length=20)
    company_website: str = Field(min_length=1, max_length=500)
    company_email: EmailStr
    federal_tax_id: str = Field(min_length=1, max_length=64)
    bbb_good_standing: bool = False
    sos_good_standing: bool = False
    corporate_liable_sales: bool = False

    @field_validator('contact_email', 'company_email')
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email(v)

    @field_validator('contact_name', 'company_name', 'address_street', 'address_city', 'address_state', 'address_zip', 'company_website', 'federal_tax_id', mode='before')
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator('contact_phone')
    @classmethod
    def check_phone(cls, v: str | None) -> str | None:
        return validate_phone(v)


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r'^\d{6}$')

    @field_validator('email')
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator('email')
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email(v)


class LoginOtpRequest(BaseModel):
    email: EmailStr

    @field_validator('email')
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email(v)


class LoginOtpVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r'^\d{6}$')

    @field_validator('email')
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email(v)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int


class MessageResponse(BaseModel):
    message: str


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: EmailStr
    role: UserRole
    user_type: str = 'CELLHUB'
    permissions: list[str]
    effective_permissions: list[str]
    tenant_id: str
    onboarding_completed: bool = False
