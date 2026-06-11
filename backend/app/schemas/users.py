from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.models.user import UserRole
from app.schemas.auth import validate_email, validate_phone


class UserSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Plain str (not EmailStr): a response echoing a trusted stored email must not
    # re-validate it, or reserved TLDs like .test would 500 on output (BUG-35).
    email: str
    mobile: str | None
    name: str
    role: UserRole
    permissions: list[str]
    effective_permissions: list[str]
    is_verified: bool
    tenant_id: str
    created_at: datetime


class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    mobile: str | None = Field(default=None)
    role: UserRole = UserRole.USER
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


class InviteUserRequest(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=255)
    role: UserRole = UserRole.USER
    tenant_id: str | None = None

    @field_validator('email')
    @classmethod
    def check_email(cls, v: str) -> str:
        return validate_email(v)

    @field_validator('name', mode='before')
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class InviteUserResponse(BaseModel):
    user: UserSummaryResponse
    email_sent: bool
    email_error: str | None = None


class UpdateUserRoleRequest(BaseModel):
    role: UserRole


class UpdateUserPermissionsRequest(BaseModel):
    permissions: list[str]


class PermissionCatalogResponse(BaseModel):
    code: str
    description: str
