import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
import hashlib
from app.core.email_domains import extract_domain, is_free_email_provider
from app.core.permissions import default_permissions_for_role
from app.core.security import hash_value, verify_value, password_strength_error
from app.core.tenancy import CELLHUB_MASTER_TENANT_ID
from app.models import AuthProvider, UserRole, UserStatus, UserType
from app.models.tenant import Tenant, TenantType
from app.models.vendor import Vendor
from app.repositories.onboarding_repository import OnboardingRepository
from app.repositories.otp_repository import OTPRepository
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_logger import audit
from app.services.email_service import EmailService
from app.services.otp_service import OTPService
from app.services.token_service import TokenService

settings = get_settings()


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.onboarding_repo = OnboardingRepository(db)
        self.otp_repo = OTPRepository(db)
        self.refresh_repo = RefreshSessionRepository(db)

    def _resolve_tenant_id(self, requested_tenant_id: str | None) -> uuid.UUID:
        if requested_tenant_id:
            # Validate the UUID shape before hitting the repo. tenant_repo.get_by_id
            # calls uuid.UUID() internally, which raises ValueError on malformed
            # input (e.g. "not-a-uuid") — uncaught, that surfaces as a 500. Convert
            # it to a clear 400 so API consumers get an actionable message.
            try:
                uuid.UUID(str(requested_tenant_id))
            except (ValueError, AttributeError, TypeError):
                raise AppError('Invalid tenant_id format', 400)
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
        # Now backed by the full env allowlist (bootstrap admin + SUPER_ADMIN_EMAILS).
        return settings.is_super_admin_email(email)

    def _ensure_bootstrap_super_admin(self, user) -> None:
        # Promote any user whose email is in the env super-admin allowlist. The env
        # list is the source of truth — we never persist "who is super admin" as a
        # manually-managed DB flag; it's derived here at auth time.
        if settings.is_super_admin_email(user.email):
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

    def signup(self, *, email: str, password: str, mobile: str | None, name: str, company_name: str):
        """Company-first signup (PLAN.md §1). The signup email's domain is the
        company key:
          - free/public email providers are rejected (must be a company email);
          - first signup for a domain creates the COMPANY tenant and makes this
            user its founding ADMIN + billing owner (ACTIVE);
          - a later signup from the same domain auto-joins that tenant as a USER
            with PENDING status, awaiting admin approval.

        The account stays unverified until the OTP flow proves control of the
        inbox — which also doubles as proof the signer controls that company
        domain's mailbox. The bootstrap super-admin promotion still happens in
        `_ensure_bootstrap_super_admin` after OTP.
        """
        email_norm = email.lower().strip()
        if self.user_repo.get_by_email(email_norm):
            raise AppError('Email already in use', 409)

        domain = extract_domain(email_norm)
        if not domain:
            raise AppError('Please enter a valid email address', 400)
        if is_free_email_provider(email_norm):
            raise AppError('Please use your company email address.', 400)

        company_name = (company_name or '').strip()
        if not company_name:
            raise AppError('Company name is required', 400)

        tenant = self.tenant_repo.get_by_email_domain(domain)
        new_tenant_created = tenant is None
        if tenant is None:
            # First account for this domain -> provision the company tenant and
            # make this user the founding ADMIN (the paying / primary user).
            tenant = Tenant(name=company_name, email_domain=domain, tenant_type=TenantType.COMPANY)
            self.db.add(tenant)
            self.db.flush()
            onboarding = self.onboarding_repo.get_or_create(tenant.id)
            onboarding.organization_name = company_name
            onboarding.admin_name = name
            onboarding.admin_email = email_norm
            role = UserRole.ADMIN
            status = UserStatus.ACTIVE
            is_billing_owner = True
        else:
            # Domain already has a company -> join as a USER pending approval.
            role = UserRole.USER
            status = UserStatus.PENDING
            is_billing_owner = False

        user = self.user_repo.create(
            email=email_norm,
            mobile=mobile,
            name=name,
            password_hash=hash_value(password),
            provider=AuthProvider.LOCAL,
            provider_id=None,
            is_verified=False,
            role=role,
            user_type=UserType.COMPANY,
            permissions=default_permissions_for_role(role),
            status=status,
            is_billing_owner=is_billing_owner,
            tenant_id=tenant.id,
        )

        self._issue_otp_for_user(user=user, purpose='signup verification')
        self.db.commit()
        audit.log(
            'user_signup',
            user_id=str(user.id),
            tenant_id=str(tenant.id),
            email=email_norm,
            role=role.value,
            account_status=status.value,
            new_tenant_created=new_tenant_created,
        )

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

        # Vendor admin must prove control of the email before login works —
        # same rule as regular signup. Prevents spammy/abusive vendor tenants.
        from app.core.permissions import default_permissions_for_role as _default_perms
        user = self.user_repo.create(
            email=contact_email.lower().strip(),
            mobile=contact_phone,
            name=contact_name,
            password_hash=hash_value(password),
            provider=AuthProvider.LOCAL,
            provider_id=None,
            is_verified=False,
            role=UserRole.ADMIN,
            user_type=UserType.VENDOR,
            permissions=_default_perms(UserRole.ADMIN),
            tenant_id=vendor_tenant.id,
        )

        # Clone-on-onboard: give the new tenant its own config set (Phase 1).
        from app.services.tenant_provisioning_service import TenantProvisioningService
        TenantProvisioningService(self.db).provision(vendor_tenant.id)

        self._issue_otp_for_user(user=user, purpose='vendor signup verification')
        self.db.commit()
        audit.log(
            'vendor_signup',
            user_id=str(user.id),
            tenant_id=str(vendor_tenant.id),
            email=user.email,
            company_name=company_name,
        )
        return user

    def _verify_otp_attempt(self, latest_otp, otp: str, *, user) -> None:
        """Check a submitted OTP against the active code, enforcing the per-OTP
        attempt limit. On a wrong code it decrements `attempts_remaining`; once
        exhausted the OTP is locked and a 429 is raised so the client can prompt
        the user to request a new code. Returns silently when the code matches.
        """
        if OTPService.verify_otp(otp, latest_otp.code_hash):
            return
        remaining = self.otp_repo.decrement_attempts(latest_otp)
        self.db.commit()
        audit.log(
            'otp_verify_failed',
            status='failure',
            level=logging.WARNING,
            user_id=str(user.id),
            email_attempted=user.email,
            attempts_remaining=remaining,
            locked=remaining <= 0,
        )
        if remaining <= 0:
            # 400, not 429: OTP-attempt exhaustion must be distinguishable from
            # the endpoint-level IP rate limit (which also returns 429). BUG-AUTH-002.
            raise AppError('Too many invalid attempts. Please request a new code.', 400)
        raise AppError(f'Invalid OTP. {remaining} attempt(s) remaining.', 400)

    def verify_otp(self, *, email: str, otp: str):
        user = self.user_repo.get_by_email(email)
        if not user:
            raise NotFoundError('User not found')

        latest_otp = self.otp_repo.get_latest_active_for_user(user.id)
        if not latest_otp:
            raise AppError('OTP expired or not found', 400)

        self._verify_otp_attempt(latest_otp, otp, user=user)

        user.is_verified = True
        self.otp_repo.mark_used(latest_otp)
        self._ensure_bootstrap_super_admin(user)
        self.db.commit()
        tokens = self._issue_tokens_for_user(user)
        audit.log(
            'otp_verified',
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            email=user.email,
            purpose='signup_verification',
        )
        return tokens

    def login(self, *, email: str, password: str):
        user = self.user_repo.get_by_email(email)
        if not user or user.provider != AuthProvider.LOCAL or not user.password_hash:
            # BUG-AUD-004: generic external `reason` per spec; granular cause
            # kept in `reason_detail` for SOC (stuffing vs enumeration).
            audit.log('user_login_failed', status='failure', level=logging.WARNING,
                      email_attempted=email, reason='invalid_credentials',
                      reason_detail='unknown_user_or_wrong_provider')
            raise UnauthorizedError('Invalid credentials')

        if not verify_value(password, user.password_hash):
            audit.log('user_login_failed', status='failure', level=logging.WARNING,
                      email_attempted=email, user_id=str(user.id),
                      reason='invalid_credentials', reason_detail='bad_password')
            raise UnauthorizedError('Invalid credentials')

        if not user.is_verified:
            audit.log('user_login_failed', status='failure', level=logging.WARNING,
                      email_attempted=email, user_id=str(user.id),
                      reason='invalid_credentials', reason_detail='not_verified')
            raise UnauthorizedError('Please verify OTP first')

        self._ensure_bootstrap_super_admin(user)
        tokens = self._issue_tokens_for_user(user)
        audit.log(
            'user_login',
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            actor_role=user.role.value,
            email=user.email,
            method='password',
        )
        return tokens

    def request_login_otp(self, *, email: str):
        user = self.user_repo.get_by_email(email)
        if not user:
            # Response stays silent (no email enumeration), but the attempt is
            # still recorded — a stream of these is an enumeration probe.
            audit.log('otp_requested', status='skipped', email_attempted=email, reason='unknown_email')
            return
        if not user.is_verified:
            raise UnauthorizedError('Please verify OTP first')

        self._enforce_otp_request_throttle(user)
        self._ensure_bootstrap_super_admin(user)
        self._issue_otp_for_user(user=user, purpose='login')
        self.db.commit()
        audit.log(
            'otp_requested',
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            email=user.email,
            purpose='login',
        )

    def _enforce_otp_request_throttle(self, user) -> None:
        """Block per-account OTP request floods (email bombing / quota drain).

        The IP-based RateLimitMiddleware stops a single noisy source; this caps
        OTPs issued to one account regardless of source IP, so a distributed
        attacker can't spam a victim's inbox or burn our email quota.
        """
        now = datetime.now(timezone.utc)

        # Short resend cooldown: a minimum gap between successive sends. This is
        # the UX/cost guard (and blocks rapid "wrong x5 -> resend" loops); the
        # window cap below is the brute-force ceiling.
        cooldown = settings.otp_resend_cooldown_seconds
        if cooldown > 0:
            last = self.otp_repo.latest_created_at(user.id)
            if last is not None:
                elapsed = (now - last).total_seconds()
                if elapsed < cooldown:
                    wait = max(1, math.ceil(cooldown - elapsed))
                    raise AppError(f'Please wait {wait} second(s) before requesting another code.', 429)

        window = timedelta(minutes=settings.otp_request_window_minutes)
        window_start = now - window
        recent = self.otp_repo.count_since(user.id, window_start)
        if recent >= settings.otp_request_max_per_window:
            # Earliest OTP in the window frees up a slot once it ages out.
            earliest = self.otp_repo.earliest_created_since(user.id, window_start)
            retry_minutes = settings.otp_request_window_minutes
            if earliest is not None:
                remaining = (earliest + window) - now
                retry_minutes = max(1, math.ceil(remaining.total_seconds() / 60))
            raise AppError(
                f'Too many OTP requests. Please try again after {retry_minutes} minute(s).',
                429,
            )

    def login_with_otp(self, *, email: str, otp: str):
        user = self.user_repo.get_by_email(email)
        if not user:
            audit.log('user_login_failed', status='failure', level=logging.WARNING,
                      email_attempted=email, reason='invalid_credentials',
                      reason_detail='unknown_user', method='otp')
            raise UnauthorizedError('Invalid OTP or email')
        if not user.is_verified:
            audit.log('user_login_failed', status='failure', level=logging.WARNING,
                      email_attempted=email, user_id=str(user.id),
                      reason='invalid_credentials', reason_detail='not_verified', method='otp')
            raise UnauthorizedError('Please verify OTP first')

        latest_otp = self.otp_repo.get_latest_active_for_user(user.id)
        if not latest_otp:
            audit.log('otp_verify_failed', status='failure', level=logging.WARNING,
                      email_attempted=email, user_id=str(user.id), reason='otp_expired_or_missing')
            raise AppError('OTP expired or not found', 400)

        self._verify_otp_attempt(latest_otp, otp, user=user)

        self.otp_repo.mark_used(latest_otp)
        self._ensure_bootstrap_super_admin(user)
        self.db.commit()
        tokens = self._issue_tokens_for_user(user)
        audit.log(
            'user_login',
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            actor_role=user.role.value,
            email=user.email,
            method='otp',
        )
        return tokens

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
            # BUG-AUTH-003: a replayed token references a now-revoked session
            # whose hash still matches (rotation reuse) — report that as a token
            # mismatch, not a generic "session invalid". A truly unknown session
            # still gets "session is invalid".
            prior = self.refresh_repo.get_by_id(int(session_id))
            if (prior and str(prior.user_id) == str(user_id)
                    and verify_value(refresh_token, prior.refresh_token_hash)):
                raise UnauthorizedError('Refresh token mismatch')
            raise UnauthorizedError('Refresh session is invalid')

        if not verify_value(refresh_token, session.refresh_token_hash):
            raise UnauthorizedError('Refresh token mismatch')

        self.refresh_repo.revoke(session)
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise UnauthorizedError('User not found')

        tokens = self._issue_tokens_for_user(user)
        # BUG-AUD-003: record the rotated-out session for revocation forensics
        # (e.g. detecting repeated refreshes from the same stolen session).
        audit.log(
            'token_refresh',
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            old_session_id=str(session.id),
        )
        return tokens

    # ── Super-admin password setup ──────────────────────────────────────────
    # Teammates listed in the env SUPER_ADMIN_EMAILS allowlist activate their
    # account via a single-use, expiring email link. The allowlist (who is a
    # super admin) lives in env; only the credential row lives in the DB, created
    # the moment they set a password here.

    @staticmethod
    def _setup_state(user) -> str:
        """A short fingerprint of the account's current password state. Binding
        the setup token to this makes it single-use: once a password is set the
        fingerprint changes, so the old link can't be replayed."""
        basis = user.password_hash if (user and user.password_hash) else 'INIT'
        return hashlib.sha256(basis.encode()).hexdigest()[:16]

    def trigger_super_admin_password_setup(self, actor: dict, email: str) -> None:
        """Existing super admin triggers a password-setup link for an allowlisted
        email. Can ONLY target an email in SUPER_ADMIN_EMAILS — never an arbitrary
        address — so it can't be used to escalate a random account."""
        if actor.get('role') != UserRole.SUPER_ADMIN.value:
            raise ForbiddenError('Only a super admin can trigger super-admin password setup')
        email_norm = (email or '').strip().lower()
        if not settings.is_super_admin_email(email_norm):
            raise ForbiddenError('That email is not in the super-admin allowlist (SUPER_ADMIN_EMAILS).')
        user = self.user_repo.get_by_email(email_norm)
        token = TokenService.create_super_admin_setup_token(email=email_norm, state=self._setup_state(user))
        link = f"{settings.frontend_url.rstrip('/')}/super-admin/set-password?token={token}"
        EmailService.send_super_admin_setup_email(to_email=email_norm, link=link)
        audit.log('super_admin_setup_link_sent', target_email=email_norm)

    def _provision_super_admin(self, email_norm: str, password: str):
        """Create or update an allowlisted super-admin's LOCAL credential row in the
        CellHub master tenant with the given password. Shared by the token-based
        (self-set) and admin-set flows."""
        master_tenant_id = uuid.UUID(CELLHUB_MASTER_TENANT_ID)
        user = self.user_repo.get_by_email(email_norm)
        if user is None:
            user = self.user_repo.create(
                email=email_norm,
                mobile=None,
                name=email_norm.split('@', 1)[0],
                password_hash=hash_value(password),
                provider=AuthProvider.LOCAL,
                provider_id=None,
                is_verified=True,
                role=UserRole.SUPER_ADMIN,
                user_type=UserType.CELLHUB,
                permissions=default_permissions_for_role(UserRole.SUPER_ADMIN),
                tenant_id=master_tenant_id,
            )
        else:
            user.password_hash = hash_value(password)
            user.provider = AuthProvider.LOCAL
            user.provider_id = None
            user.is_verified = True
            user.role = UserRole.SUPER_ADMIN
            user.permissions = default_permissions_for_role(UserRole.SUPER_ADMIN)
            self.db.flush()
        self.db.commit()
        return user

    def set_super_admin_password(self, *, token: str, password: str):
        """Consume a setup token and set the super admin's password (self-set flow).
        Validates signature/TTL/type, re-checks allowlist, enforces single-use via
        the state binding, and requires a strong password."""
        payload = TokenService.decode_super_admin_setup_token(token)
        email_norm = (payload.get('email') or '').strip().lower()
        if not settings.is_super_admin_email(email_norm):
            raise UnauthorizedError('This setup link is no longer valid.')
        user = self.user_repo.get_by_email(email_norm)
        if payload.get('state') != self._setup_state(user):
            raise UnauthorizedError('This setup link has already been used or is no longer valid.')
        err = password_strength_error(password)
        if err:
            raise AppError(err, 422)
        user = self._provision_super_admin(email_norm, password)
        audit.log('super_admin_credentials_changed', user_id=str(user.id),
                  target_email=email_norm, flow='setup_token')
        return {'email': email_norm}

    def admin_set_super_admin_credentials(self, actor: dict, *, email: str, password: str):
        """Admin-set flow: an existing super admin directly sets the password for an
        allowlisted teammate (no email round-trip). Restricted to SUPER_ADMIN_EMAILS
        so it can't set credentials for an arbitrary account."""
        if actor.get('role') != UserRole.SUPER_ADMIN.value:
            raise ForbiddenError('Only a super admin can set super-admin credentials')
        email_norm = (email or '').strip().lower()
        if not settings.is_super_admin_email(email_norm):
            raise ForbiddenError('That email is not in the super-admin allowlist (SUPER_ADMIN_EMAILS).')
        err = password_strength_error(password)
        if err:
            raise AppError(err, 422)
        user = self._provision_super_admin(email_norm, password)
        audit.log('super_admin_credentials_changed', user_id=str(user.id),
                  target_email=email_norm, flow='admin_set')
        return {'email': email_norm}

    def logout(self, refresh_token: str):
        payload = TokenService.decode_token(refresh_token)
        sid = payload.get('sid')
        if not sid:
            return

        session = self.refresh_repo.get_active_by_id(int(sid))
        if session:
            self.refresh_repo.revoke(session)
            self.db.commit()
            # BUG-AUD-002: record which session was revoked, not just the user.
            audit.log('user_logout', user_id=str(session.user_id), session_id=str(session.id))

    def oauth_login_or_register(self, *, provider: AuthProvider, email: str, name: str, provider_id: str):
        user = self.user_repo.get_by_email(email)
        new_user_created = user is None
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
        tokens = self._issue_tokens_for_user(user)
        audit.log(
            'oauth_login',
            user_id=str(user.id),
            tenant_id=str(user.tenant_id),
            actor_role=user.role.value if hasattr(user.role, 'value') else str(user.role),
            email=user.email,
            provider=provider.value if hasattr(provider, 'value') else str(provider),
            new_user_created=new_user_created,
        )
        return tokens
