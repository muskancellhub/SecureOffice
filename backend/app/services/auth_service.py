import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError, UnauthorizedError
from app.core.permissions import default_permissions_for_role
from app.core.security import hash_value, verify_value
from app.models import AuthProvider, UserRole, UserType
from app.models.tenant import TenantType
from app.models.vendor import Vendor
from app.repositories.otp_repository import OTPRepository
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.email_service import EmailService
from app.services.otp_service import OTPService
from app.services.token_service import TokenService

settings = get_settings()


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.otp_repo = OTPRepository(db)
        self.refresh_repo = RefreshSessionRepository(db)

    def _resolve_tenant_id(self, requested_tenant_id: str | None) -> uuid.UUID:
        if requested_tenant_id:
            tenant = self.tenant_repo.get_by_id(requested_tenant_id)
            if not tenant:
                raise NotFoundError('Tenant not found')
            return tenant.id

        if settings.default_tenant_id:
            tenant = self.tenant_repo.get_by_id(settings.default_tenant_id)
            if tenant:
                return tenant.id

        tenant = self.tenant_repo.get_first()
        if not tenant:
            raise AppError('No tenant found. Create a tenant first.', 400)
        return tenant.id

    def _is_bootstrap_super_admin(self, email: str) -> bool:
        if not settings.bootstrap_super_admin_email:
            return False
        return email.lower().strip() == settings.bootstrap_super_admin_email.lower().strip()

    def _ensure_bootstrap_super_admin(self, user) -> None:
        if self._is_bootstrap_super_admin(user.email):
            user.role = UserRole.SUPER_ADMIN
            user.permissions = default_permissions_for_role(UserRole.SUPER_ADMIN)
            user.is_verified = True
            self.db.flush()

    def _ensure_permissions_initialized(self, user) -> None:
        if user.permissions:
            return
        user.permissions = default_permissions_for_role(user.role)
        self.db.flush()

    def _issue_otp_for_user(self, *, user, purpose: str) -> None:
        otp = OTPService.generate_otp()
        self.otp_repo.create(
            user_id=user.id,
            code_hash=OTPService.hash_otp(otp),
            expires_at=OTPService.otp_expiry(),
        )
        EmailService.send_otp_email(to_email=user.email, otp=otp, purpose=purpose)

    def signup(self, *, email: str, password: str, mobile: str | None, name: str, tenant_id: str | None):
        existing = self.user_repo.get_by_email(email)
        if existing:
            raise AppError('Email already in use', 409)

        is_bootstrap_super_admin = self._is_bootstrap_super_admin(email)
        resolved_tenant_id = self._resolve_tenant_id(tenant_id)
        user = self.user_repo.create(
            email=email.lower().strip(),
            mobile=mobile,
            name=name,
            password_hash=hash_value(password),
            provider=AuthProvider.LOCAL,
            provider_id=None,
            is_verified=is_bootstrap_super_admin,
            role=UserRole.SUPER_ADMIN if is_bootstrap_super_admin else UserRole.USER,
            user_type=UserType.CELLHUB,
            permissions=default_permissions_for_role(UserRole.SUPER_ADMIN if is_bootstrap_super_admin else UserRole.USER),
            tenant_id=resolved_tenant_id,
        )

        if not is_bootstrap_super_admin:
            self._issue_otp_for_user(user=user, purpose='signup verification')

        self.db.commit()

        if is_bootstrap_super_admin:
            print(f"[BOOTSTRAP SUPER ADMIN] email={email} created and auto-verified")

    def vendor_signup(
        self,
        *,
        contact_name: str,
        contact_email: str,
        contact_phone: str | None,
        password: str,
        company_name: str,
        address_street: str,
        address_city: str,
        address_state: str,
        address_zip: str,
        company_website: str,
        company_email: str,
        federal_tax_id: str,
        bbb_good_standing: bool,
        sos_good_standing: bool,
        corporate_liable_sales: bool,
    ):
        existing = self.user_repo.get_by_email(contact_email)
        if existing:
            raise AppError('Email already in use', 409)

        from app.models.tenant import Tenant
        vendor_tenant = Tenant(name=company_name, tenant_type=TenantType.VENDOR)
        self.db.add(vendor_tenant)
        self.db.flush()

        vendor_profile = Vendor(
            tenant_id=vendor_tenant.id,
            company_name=company_name,
            address_street=address_street,
            address_city=address_city,
            address_state=address_state,
            address_zip=address_zip,
            company_website=company_website,
            company_email=company_email,
            federal_tax_id=federal_tax_id,
            bbb_good_standing=bbb_good_standing,
            sos_good_standing=sos_good_standing,
            corporate_liable_sales=corporate_liable_sales,
            is_approved=False,
        )
        self.db.add(vendor_profile)
        self.db.flush()

        from app.core.permissions import default_permissions_for_role as _default_perms
        user = self.user_repo.create(
            email=contact_email.lower().strip(),
            mobile=contact_phone,
            name=contact_name,
            password_hash=hash_value(password),
            provider=AuthProvider.LOCAL,
            provider_id=None,
            is_verified=True,
            role=UserRole.ADMIN,
            user_type=UserType.VENDOR,
            permissions=_default_perms(UserRole.ADMIN),
            tenant_id=vendor_tenant.id,
        )

        self.db.commit()
        return user

    def verify_otp(self, *, email: str, otp: str):
        user = self.user_repo.get_by_email(email)
        if not user:
            raise NotFoundError('User not found')

        latest_otp = self.otp_repo.get_latest_active_for_user(user.id)
        if not latest_otp:
            raise AppError('OTP expired or not found', 400)

        if not OTPService.verify_otp(otp, latest_otp.code_hash):
            raise AppError('Invalid OTP', 400)

        user.is_verified = True
        self.otp_repo.mark_used(latest_otp)
        self._ensure_bootstrap_super_admin(user)
        self.db.commit()
        return self._issue_tokens_for_user(user)

    def login(self, *, email: str, password: str):
        user = self.user_repo.get_by_email(email)
        if not user or user.provider != AuthProvider.LOCAL or not user.password_hash:
            raise UnauthorizedError('Invalid credentials')

        if not verify_value(password, user.password_hash):
            raise UnauthorizedError('Invalid credentials')

        if not user.is_verified:
            raise UnauthorizedError('Please verify OTP first')

        self._ensure_bootstrap_super_admin(user)
        return self._issue_tokens_for_user(user)

    def request_login_otp(self, *, email: str):
        user = self.user_repo.get_by_email(email)
        if not user:
            return
        if not user.is_verified:
            raise UnauthorizedError('Please verify OTP first')

        self._ensure_bootstrap_super_admin(user)
        self._issue_otp_for_user(user=user, purpose='login')
        self.db.commit()

    def login_with_otp(self, *, email: str, otp: str):
        user = self.user_repo.get_by_email(email)
        if not user:
            raise UnauthorizedError('Invalid OTP or email')
        if not user.is_verified:
            raise UnauthorizedError('Please verify OTP first')

        latest_otp = self.otp_repo.get_latest_active_for_user(user.id)
        if not latest_otp:
            raise AppError('OTP expired or not found', 400)
        if not OTPService.verify_otp(otp, latest_otp.code_hash):
            raise AppError('Invalid OTP', 400)

        self.otp_repo.mark_used(latest_otp)
        self._ensure_bootstrap_super_admin(user)
        self.db.commit()
        return self._issue_tokens_for_user(user)

    def _issue_tokens_for_user(self, user):
        self._ensure_permissions_initialized(user)
        refresh_expiry = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
        session = self.refresh_repo.create_placeholder(user_id=user.id, expires_at=refresh_expiry)

        refresh_token = TokenService.create_refresh_token(user_id=str(user.id), session_id=session.id)
        session.refresh_token_hash = hash_value(refresh_token)

        user_type_val = user.user_type.value if hasattr(user.user_type, 'value') else str(user.user_type)
        tenant_type_val = 'CELLHUB'
        if user.tenant:
            tt = user.tenant.tenant_type
            tenant_type_val = tt.value if hasattr(tt, 'value') else str(tt)

        access_token = TokenService.create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role.value,
            user_type=user_type_val,
            tenant_id=str(user.tenant_id),
            tenant_type=tenant_type_val,
        )

        self.db.commit()

        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in': settings.access_token_expire_minutes * 60,
        }

    def refresh(self, refresh_token: str):
        payload = TokenService.decode_token(refresh_token)
        if payload.get('type') != 'refresh':
            raise UnauthorizedError('Invalid refresh token')

        user_id = payload.get('user_id')
        session_id = payload.get('sid')
        if not user_id or not session_id:
            raise UnauthorizedError('Invalid refresh token payload')

        session = self.refresh_repo.get_active_by_id(int(session_id))
        if not session or str(session.user_id) != str(user_id):
            raise UnauthorizedError('Refresh session is invalid')

        if not verify_value(refresh_token, session.refresh_token_hash):
            raise UnauthorizedError('Refresh token mismatch')

        self.refresh_repo.revoke(session)
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise UnauthorizedError('User not found')

        return self._issue_tokens_for_user(user)

    def logout(self, refresh_token: str):
        payload = TokenService.decode_token(refresh_token)
        sid = payload.get('sid')
        if not sid:
            return

        session = self.refresh_repo.get_active_by_id(int(sid))
        if session:
            self.refresh_repo.revoke(session)
            self.db.commit()

    def oauth_login_or_register(self, *, provider: AuthProvider, email: str, name: str, provider_id: str):
        user = self.user_repo.get_by_email(email)
        if not user:
            tenant_id = self._resolve_tenant_id(None)
            user = self.user_repo.create(
                email=email.lower().strip(),
                mobile=None,
                name=name or email.split('@')[0],
                password_hash=None,
                provider=provider,
                provider_id=provider_id,
                is_verified=True,
                role=UserRole.SUPER_ADMIN if self._is_bootstrap_super_admin(email) else UserRole.USER,
                user_type=UserType.CELLHUB,
                permissions=default_permissions_for_role(
                    UserRole.SUPER_ADMIN if self._is_bootstrap_super_admin(email) else UserRole.USER
                ),
                tenant_id=tenant_id,
            )
            self.db.flush()
        else:
            self._ensure_bootstrap_super_admin(user)
        return self._issue_tokens_for_user(user)
