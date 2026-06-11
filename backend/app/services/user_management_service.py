import logging
import secrets
import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
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
from app.schemas.users import CreateUserRequest, InviteUserRequest
from app.services.audit_logger import audit
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


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
        audit.log('permission_catalog_viewed', level=logging.INFO)
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

        try:
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
        except IntegrityError:
            # The get_by_email pre-check above is not atomic: a concurrent request
            # can insert the same email between the check and the flush/commit here.
            # The DB's unique constraint is the real guard — turn its violation into
            # a clean 409 instead of an unhandled 500 (BUG-USER-002). The INSERT is
            # emitted by create()'s flush, so the guard must cover it too.
            self.db.rollback()
            raise AppError('Email already in use', 409)
        self.db.refresh(user)
        audit.log(
            'user_created',
            target_user_id=str(user.id),
            target_email=user.email,
            target_role=user.role.value,
            target_tenant_id=str(user.tenant_id),
        )
        return user

    def invite_user(self, actor: dict, payload: InviteUserRequest):
        """Create a user from an email invite and send them a sign-in email.

        Reuses create_user (which enforces all role/permission checks). The
        invitee logs in passwordlessly via OTP, so we set a random password
        they never need to use.
        """
        name = payload.name or payload.email.split('@')[0]
        create_req = CreateUserRequest(
            email=payload.email,
            name=name,
            password=secrets.token_urlsafe(24),
            role=payload.role,
            tenant_id=payload.tenant_id,
        )
        user = self.create_user(actor, create_req)

        # Send the invite email. The account is already created, so an email
        # failure must not roll it back — but we DO report it back to the caller
        # so the UI can tell the admin the invite mail didn't actually go out
        # (e.g. Resend quota exhausted / sandbox key / unverified recipient).
        email_sent = False
        email_error: str | None = None
        try:
            tenant = self.tenant_repo.get_by_id(user.tenant_id)
            org_name = getattr(tenant, 'name', None) or 'your team'
            inviter = self.user_repo.get_by_id(actor['user_id'])
            invited_by = getattr(inviter, 'name', None) or getattr(inviter, 'email', None)
            settings = get_settings()
            login_url = f"{(settings.frontend_url or '').rstrip('/')}/login"
            EmailService.send_invite_email(
                to_email=user.email,
                org_name=org_name,
                invited_by=invited_by,
                login_url=login_url,
            )
            email_sent = True
        except Exception as exc:  # noqa: BLE001
            email_error = str(exc) or exc.__class__.__name__
            logger.exception('[INVITE EMAIL FAILED] to=%s', user.email)

        audit.log(
            'user_invited',
            target_user_id=str(user.id),
            target_email=user.email,
            target_role=user.role.value,
            email_sent=email_sent,
        )
        return user, email_sent, email_error

    def list_users(self, actor: dict, tenant_id: str | None = None):
        actor_role = self._actor_role(actor)
        actor_permissions = self._actor_effective_permissions(actor, actor_role)
        self._assert_actor_can_manage(actor_role, actor_permissions)

        actor_tenant_id = actor['tenant_id']
        if actor_role == UserRole.SUPER_ADMIN:
            if tenant_id:
                tenant_uuid = self._parse_tenant_uuid(tenant_id)
                users = self.user_repo.list_by_tenant(str(tenant_uuid))
            else:
                users = self.user_repo.list_all()
        else:
            if tenant_id:
                tenant_uuid = self._parse_tenant_uuid(tenant_id)
                if str(tenant_uuid) != actor_tenant_id:
                    raise ForbiddenError('ADMIN can only view users in their own tenant')
            users = self.user_repo.list_by_tenant(actor_tenant_id)
        audit.log('user_list_viewed', level=logging.INFO,
                  tenant_filter=tenant_id, result_count=len(users))
        return users

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

        old_role = target_user.role
        target_user.role = new_role
        target_user.permissions = default_permissions_for_role(new_role)
        self.db.commit()
        self.db.refresh(target_user)
        audit.log(
            'user_role_changed',
            target_user_id=str(target_user.id),
            target_email=target_user.email,
            old_role=old_role.value,
            new_role=new_role.value,
        )
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

        # Reject unknown codes BEFORE normalize_permissions() silently strips them.
        # Without this, an all-unknown payload normalizes to [], the any()-check
        # below sees an empty list and never fires, and the bad input is masked as
        # a 200 that wipes the user's permissions (BUG-USER-001).
        unknown = [p for p in permissions if str(p).strip() not in PERMISSION_CATALOG]
        if unknown:
            raise AppError('One or more permissions are invalid for target role', 400)

        normalized = normalize_permissions(permissions)
        allowed = set(allowed_permissions_for_role(target_user.role))
        if any(p not in allowed for p in normalized):
            raise AppError('One or more permissions are invalid for target role', 400)

        old_permissions = set(normalize_permissions(target_user.permissions))
        target_user.permissions = normalized
        self.db.commit()
        self.db.refresh(target_user)
        new_permissions = set(normalized)
        audit.log(
            'user_permissions_changed',
            target_user_id=str(target_user.id),
            target_email=target_user.email,
            added=sorted(new_permissions - old_permissions),
            removed=sorted(old_permissions - new_permissions),
        )
        return target_user
