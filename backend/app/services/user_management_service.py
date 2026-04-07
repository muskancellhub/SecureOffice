import uuid
from sqlalchemy.orm import Session
from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.core.permissions import (
    PERMISSION_CATALOG,
    PERM_MANAGE_ADMINS,
    PERM_MANAGE_PERMISSIONS,
    PERM_MANAGE_USERS,
    allowed_permissions_for_role,
    default_permissions_for_role,
    effective_permissions_for_role,
    normalize_permissions,
)
from app.core.security import hash_value
from app.models import AuthProvider, UserRole
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.schemas.users import CreateUserRequest


class UserManagementService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.tenant_repo = TenantRepository(db)

    def _actor_role(self, actor: dict) -> UserRole:
        return UserRole(actor['role'])

    @staticmethod
    def _parse_tenant_uuid(tenant_id: str, *, field_name: str = 'tenant_id') -> uuid.UUID:
        try:
            return uuid.UUID(str(tenant_id))
        except (ValueError, TypeError):
            raise AppError(f'Invalid {field_name}', 400)

    def _actor_effective_permissions(self, actor: dict, actor_role: UserRole) -> set[str]:
        actor_user = self.user_repo.get_by_id(actor['user_id'])
        if not actor_user:
            raise ForbiddenError('Actor user not found')
        return set(effective_permissions_for_role(actor_role, actor_user.permissions))

    def _assert_actor_can_manage(self, actor_role: UserRole, actor_permissions: set[str]) -> None:
        if actor_role not in {UserRole.SUPER_ADMIN, UserRole.ADMIN}:
            raise ForbiddenError('Only ADMIN or SUPER_ADMIN can manage users')
        if PERM_MANAGE_USERS not in actor_permissions:
            raise ForbiddenError('Missing permission: manage_users')

    def _assert_actor_can_create_role(self, actor_role: UserRole, actor_permissions: set[str], target_role: UserRole) -> None:
        if target_role == UserRole.SUPER_ADMIN:
            raise ForbiddenError('SUPER_ADMIN accounts cannot be created from this console')
        if actor_role == UserRole.SUPER_ADMIN and target_role == UserRole.USER:
            return
        if actor_role == UserRole.SUPER_ADMIN and target_role == UserRole.ADMIN:
            if PERM_MANAGE_ADMINS not in actor_permissions:
                raise ForbiddenError('Missing permission: manage_admins')
            return
        if actor_role == UserRole.ADMIN and target_role == UserRole.USER:
            return
        raise ForbiddenError('Insufficient role permission to create this user type')

    def _resolve_tenant_for_creation(self, actor: dict, actor_role: UserRole, requested_tenant_id: str | None) -> uuid.UUID:
        actor_tenant_id = self._parse_tenant_uuid(actor['tenant_id'], field_name='actor tenant_id')

        if actor_role == UserRole.SUPER_ADMIN:
            if not requested_tenant_id:
                return actor_tenant_id
            requested_tenant_uuid = self._parse_tenant_uuid(requested_tenant_id)
            tenant = self.tenant_repo.get_by_id(str(requested_tenant_uuid))
            if not tenant:
                raise NotFoundError('Tenant not found')
            return tenant.id

        if requested_tenant_id:
            requested_tenant_uuid = self._parse_tenant_uuid(requested_tenant_id)
            if requested_tenant_uuid != actor_tenant_id:
                raise ForbiddenError('ADMIN can only manage users in their own tenant')
        return actor_tenant_id

    @staticmethod
    def serialize_user(user) -> dict:
        effective_permissions = effective_permissions_for_role(user.role, user.permissions)
        return {
            'id': str(user.id),
            'email': user.email,
            'mobile': user.mobile,
            'name': user.name,
            'role': user.role,
            'permissions': normalize_permissions(user.permissions),
            'effective_permissions': effective_permissions,
            'is_verified': user.is_verified,
            'tenant_id': str(user.tenant_id),
            'created_at': user.created_at,
        }

    def list_permission_catalog(self, actor: dict) -> list[dict]:
        actor_role = self._actor_role(actor)
        actor_permissions = self._actor_effective_permissions(actor, actor_role)
        self._assert_actor_can_manage(actor_role, actor_permissions)
        if PERM_MANAGE_PERMISSIONS not in actor_permissions:
            raise ForbiddenError('Missing permission: manage_permissions')
        return [{'code': code, 'description': desc} for code, desc in PERMISSION_CATALOG.items()]

    def create_user(self, actor: dict, payload: CreateUserRequest):
        actor_role = self._actor_role(actor)
        actor_permissions = self._actor_effective_permissions(actor, actor_role)
        self._assert_actor_can_manage(actor_role, actor_permissions)
        self._assert_actor_can_create_role(actor_role, actor_permissions, payload.role)

        existing = self.user_repo.get_by_email(payload.email)
        if existing:
            raise AppError('Email already in use', 409)

        tenant_id = self._resolve_tenant_for_creation(actor, actor_role, payload.tenant_id)

        user = self.user_repo.create(
            email=payload.email.lower().strip(),
            mobile=payload.mobile,
            name=payload.name,
            password_hash=hash_value(payload.password),
            provider=AuthProvider.LOCAL,
            provider_id=None,
            is_verified=True,
            role=payload.role,
            permissions=default_permissions_for_role(payload.role),
            tenant_id=tenant_id,
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def list_users(self, actor: dict, tenant_id: str | None = None):
        actor_role = self._actor_role(actor)
        actor_permissions = self._actor_effective_permissions(actor, actor_role)
        self._assert_actor_can_manage(actor_role, actor_permissions)

        actor_tenant_id = actor['tenant_id']
        if actor_role == UserRole.SUPER_ADMIN:
            if tenant_id:
                tenant_uuid = self._parse_tenant_uuid(tenant_id)
                return self.user_repo.list_by_tenant(str(tenant_uuid))
            return self.user_repo.list_all()

        if tenant_id:
            tenant_uuid = self._parse_tenant_uuid(tenant_id)
            if str(tenant_uuid) != actor_tenant_id:
                raise ForbiddenError('ADMIN can only view users in their own tenant')
        return self.user_repo.list_by_tenant(actor_tenant_id)

    def update_user_role(self, actor: dict, target_user_id: str, new_role: UserRole):
        actor_role = self._actor_role(actor)
        actor_permissions = self._actor_effective_permissions(actor, actor_role)
        self._assert_actor_can_manage(actor_role, actor_permissions)

        target_user = self.user_repo.get_by_id(target_user_id)
        if not target_user:
            raise NotFoundError('Target user not found')

        if target_user.role == UserRole.SUPER_ADMIN:
            raise ForbiddenError('SUPER_ADMIN accounts cannot be modified here')
        if new_role == UserRole.SUPER_ADMIN:
            raise ForbiddenError('Cannot assign SUPER_ADMIN role from this console')

        if actor_role == UserRole.SUPER_ADMIN and (target_user.role == UserRole.ADMIN or new_role == UserRole.ADMIN):
            if PERM_MANAGE_ADMINS not in actor_permissions:
                raise ForbiddenError('Missing permission: manage_admins')

        if actor_role == UserRole.ADMIN:
            if str(target_user.tenant_id) != actor['tenant_id']:
                raise ForbiddenError('ADMIN can only manage users in their own tenant')
            if target_user.role != UserRole.USER or new_role != UserRole.USER:
                raise ForbiddenError('ADMIN can only manage USER role accounts')

        target_user.role = new_role
        target_user.permissions = default_permissions_for_role(new_role)
        self.db.commit()
        self.db.refresh(target_user)
        return target_user

    def update_user_permissions(self, actor: dict, target_user_id: str, permissions: list[str]):
        actor_role = self._actor_role(actor)
        actor_permissions = self._actor_effective_permissions(actor, actor_role)
        self._assert_actor_can_manage(actor_role, actor_permissions)
        if PERM_MANAGE_PERMISSIONS not in actor_permissions:
            raise ForbiddenError('Missing permission: manage_permissions')

        target_user = self.user_repo.get_by_id(target_user_id)
        if not target_user:
            raise NotFoundError('Target user not found')
        if target_user.role == UserRole.SUPER_ADMIN:
            raise ForbiddenError('SUPER_ADMIN permissions cannot be modified here')

        if actor_role == UserRole.ADMIN:
            if str(target_user.tenant_id) != actor['tenant_id']:
                raise ForbiddenError('ADMIN can only manage users in their own tenant')
            if target_user.role != UserRole.USER:
                raise ForbiddenError('ADMIN can only edit permissions for USER accounts')

        normalized = normalize_permissions(permissions)
        allowed = set(allowed_permissions_for_role(target_user.role))
        if any(p not in allowed for p in normalized):
            raise AppError('One or more permissions are invalid for target role', 400)

        target_user.permissions = normalized
        self.db.commit()
        self.db.refresh(target_user)
        return target_user
