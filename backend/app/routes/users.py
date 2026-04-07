from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.middleware.dependencies import get_current_user
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth import MeResponse
from app.schemas.users import (
    CreateUserRequest,
    PermissionCatalogResponse,
    UpdateUserPermissionsRequest,
    UpdateUserRoleRequest,
    UserSummaryResponse,
)
from app.services.user_management_service import UserManagementService
from app.services.onboarding_service import OnboardingService

router = APIRouter(prefix='/users', tags=['Users'])


def _to_user_response(user) -> UserSummaryResponse:
    data = UserManagementService.serialize_user(user)
    return UserSummaryResponse(
        id=data['id'],
        email=data['email'],
        mobile=data['mobile'],
        name=data['name'],
        role=UserRole(data['role']),
        permissions=data['permissions'],
        effective_permissions=data['effective_permissions'],
        is_verified=data['is_verified'],
        tenant_id=data['tenant_id'],
        created_at=data['created_at'],
    )


@router.get('/me', response_model=MeResponse)
def me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    onboarding_service = OnboardingService(db)
    onboarding_completed = onboarding_service.is_onboarding_complete(current_user['tenant_id'])
    user = UserRepository(db).get_by_id(current_user['user_id'])
    if not user:
        return MeResponse(
            user_id=current_user['user_id'],
            email=current_user['email'],
            role=current_user['role'],
            permissions=[],
            effective_permissions=[],
            tenant_id=current_user['tenant_id'],
            onboarding_completed=onboarding_completed,
        )
    serialized = UserManagementService.serialize_user(user)
    return MeResponse(
        user_id=serialized['id'],
        email=serialized['email'],
        role=serialized['role'],
        permissions=serialized['permissions'],
        effective_permissions=serialized['effective_permissions'],
        tenant_id=serialized['tenant_id'],
        onboarding_completed=onboarding_completed,
    )


@router.get('/permissions/catalog', response_model=list[PermissionCatalogResponse])
def list_permission_catalog(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = UserManagementService(db).list_permission_catalog(current_user)
    return [PermissionCatalogResponse(code=row['code'], description=row['description']) for row in rows]


@router.post('', response_model=UserSummaryResponse)
def create_user(payload: CreateUserRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = UserManagementService(db).create_user(current_user, payload)
    return _to_user_response(user)


@router.get('', response_model=list[UserSummaryResponse])
def list_users(
    tenant_id: str | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = UserManagementService(db).list_users(current_user, tenant_id=tenant_id)
    return [_to_user_response(user) for user in users]


@router.patch('/{user_id}/role', response_model=UserSummaryResponse)
def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = UserManagementService(db).update_user_role(current_user, user_id, payload.role)
    return _to_user_response(user)


@router.patch('/{user_id}/permissions', response_model=UserSummaryResponse)
def update_user_permissions(
    user_id: str,
    payload: UpdateUserPermissionsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = UserManagementService(db).update_user_permissions(current_user, user_id, payload.permissions)
    return _to_user_response(user)
