from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.user import UserRole


class UserSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
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
    mobile: str | None = Field(default=None, max_length=32)
    role: UserRole = UserRole.USER
    tenant_id: str | None = None


class UpdateUserRoleRequest(BaseModel):
    role: UserRole


class UpdateUserPermissionsRequest(BaseModel):
    permissions: list[str]


class PermissionCatalogResponse(BaseModel):
    code: str
    description: str
