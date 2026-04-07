from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.user import UserRole


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    mobile: str | None = Field(default=None, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    tenant_id: str | None = None


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
    permissions: list[str]
    effective_permissions: list[str]
    tenant_id: str
    onboarding_completed: bool = False
