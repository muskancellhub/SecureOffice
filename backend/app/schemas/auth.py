from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.user import UserRole, UserType


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    mobile: str | None = Field(default=None, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    tenant_id: str | None = None


class VendorSignupRequest(BaseModel):
    contact_name: str = Field(min_length=1, max_length=255)
    contact_email: EmailStr
    contact_phone: str | None = Field(default=None, max_length=32)
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


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r'^\d{6}$')


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginOtpRequest(BaseModel):
    email: EmailStr


class LoginOtpVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(pattern=r'^\d{6}$')


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
