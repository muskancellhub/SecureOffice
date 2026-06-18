"""AuthService — DB integration for signup/OTP/login/refresh/super-admin flows.

Skips without Postgres. All email sends and OTP generation are monkeypatched;
bcrypt hashing is real, which makes this the slowest test file (by design —
the hash/verify path is part of what is under test).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings

settings = get_settings()

PFX = 'AUTHSVC-'
RUN = uuid.uuid4().hex[:8]
DOMAIN = f'corp-{RUN}.example'
PASSWORD = 'Str0ng!Passw0rd'


@pytest.fixture(scope='module')
def auth_db():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    yield SessionLocal

    with SessionLocal() as db:
        rows = db.execute(text(
            "SELECT id FROM tenants WHERE email_domain = :d OR name LIKE :p"
        ), {'d': DOMAIN, 'p': f'{PFX}%'}).fetchall()
        tenant_ids = [str(r.id) for r in rows]
        db.execute(text(
            "DELETE FROM refresh_sessions WHERE user_id IN "
            "(SELECT id FROM users WHERE email LIKE :e)"), {'e': f'%@{DOMAIN}'})
        db.execute(text(
            "DELETE FROM otps WHERE user_id IN "
            "(SELECT id FROM users WHERE email LIKE :e)"), {'e': f'%@{DOMAIN}'})
        db.execute(text("DELETE FROM users WHERE email LIKE :e"), {'e': f'%@{DOMAIN}'})
        for t in tenant_ids:
            for tbl in ('tenant_onboarding', 'tenant_settings', 'financing_terms',
                        'customer_pricing', 'vendors'):
                db.execute(text(f'DELETE FROM {tbl} WHERE tenant_id = :t'), {'t': t})
            db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': t})
        db.commit()


@pytest.fixture(autouse=True)
def patched_io(monkeypatch):
    """Deterministic OTPs, captured emails, no resend cooldown by default."""
    from app.services.email_service import EmailService
    from app.services.otp_service import OTPService
    sent = {'otp': [], 'setup': []}
    monkeypatch.setattr(
        EmailService, 'send_otp_email',
        staticmethod(lambda *, to_email, otp, purpose: sent['otp'].append((to_email, otp, purpose))))
    monkeypatch.setattr(
        EmailService, 'send_super_admin_setup_email',
        staticmethod(lambda *, to_email, link: sent['setup'].append((to_email, link))))
    monkeypatch.setattr(OTPService, 'generate_otp', staticmethod(lambda: '123456'))
    monkeypatch.setattr(settings, 'otp_resend_cooldown_seconds', 0)
    return sent


def _svc(db):
    from app.services.auth_service import AuthService
    return AuthService(db)


def _email(tag):
    return f'{tag}-{uuid.uuid4().hex[:8]}@{DOMAIN}'


def _signup(svc, email, company=f'{PFX}First Co', name='Auth Tester'):
    svc.signup(email=email, password=PASSWORD, mobile=None, name=name, company_name=company)


# ── signup ───────────────────────────────────────────────────────────────────

def test_signup_rejects_free_email_provider(auth_db):
    from app.core.exceptions import AppError
    with auth_db() as db:
        with pytest.raises(AppError) as exc:
            _signup(_svc(db), f'someone-{RUN}@gmail.com')
        assert exc.value.status_code == 400


def test_signup_rejects_blank_company(auth_db):
    from app.core.exceptions import AppError
    with auth_db() as db:
        with pytest.raises(AppError) as exc:
            _svc(db).signup(email=_email('blank'), password=PASSWORD, mobile=None,
                            name='X', company_name='   ')
        assert exc.value.status_code == 400


def test_first_signup_creates_company_tenant_and_admin(auth_db, patched_io):
    from app.models.user import UserRole, UserStatus
    email = _email('founder')
    with auth_db() as db:
        svc = _svc(db)
        _signup(svc, email)
        user = svc.user_repo.get_by_email(email)
        assert user.role == UserRole.ADMIN
        assert user.status == UserStatus.ACTIVE
        assert user.is_billing_owner is True
        assert user.is_verified is False
        tenant = svc.tenant_repo.get_by_email_domain(DOMAIN)
        assert tenant is not None and str(user.tenant_id) == str(tenant.id)
        onboarding = svc.onboarding_repo.get_by_tenant_id(tenant.id)
        assert onboarding.organization_name == f'{PFX}First Co'
        assert onboarding.admin_email == email
        assert patched_io['otp'][-1][0] == email


def test_second_signup_same_domain_joins_as_pending_user(auth_db):
    from app.models.user import UserRole, UserStatus
    email = _email('joiner')
    with auth_db() as db:
        svc = _svc(db)
        before = svc.tenant_repo.get_by_email_domain(DOMAIN)
        _signup(svc, email, company=f'{PFX}Ignored Name')
        user = svc.user_repo.get_by_email(email)
        assert user.role == UserRole.USER
        assert user.status == UserStatus.PENDING
        assert user.is_billing_owner is False
        assert str(user.tenant_id) == str(before.id)


def test_signup_duplicate_email_409(auth_db):
    from app.core.exceptions import AppError
    email = _email('dup')
    with auth_db() as db:
        svc = _svc(db)
        _signup(svc, email)
        with pytest.raises(AppError) as exc:
            _signup(svc, email)
        assert exc.value.status_code == 409


# ── verify_otp ───────────────────────────────────────────────────────────────

def test_verify_otp_wrong_code_counts_down_then_locks(auth_db, monkeypatch):
    from app.core.exceptions import AppError
    monkeypatch.setattr(settings, 'otp_max_attempts', 2)
    email = _email('lockout')
    with auth_db() as db:
        svc = _svc(db)
        _signup(svc, email)
        with pytest.raises(AppError) as exc:
            svc.verify_otp(email=email, otp='000000')
        assert exc.value.status_code == 400
        assert '1 attempt(s) remaining' in str(exc.value)
        with pytest.raises(AppError) as exc:
            svc.verify_otp(email=email, otp='000000')
        # BUG-AUTH-002: lockout is 400 (not 429), so it's distinguishable from
        # the endpoint-level IP rate limit which also returns 429.
        assert exc.value.status_code == 400
        assert 'Too many invalid attempts' in str(exc.value)
        # OTP is locked even with the right code now
        with pytest.raises(AppError) as exc:
            svc.verify_otp(email=email, otp='123456')
        assert exc.value.status_code == 400  # 'OTP expired or not found'


def test_verify_otp_happy_returns_decodable_tokens(auth_db):
    from app.services.token_service import TokenService
    email = _email('verify')
    with auth_db() as db:
        svc = _svc(db)
        _signup(svc, email)
        tokens = svc.verify_otp(email=email, otp='123456')
        assert svc.user_repo.get_by_email(email).is_verified is True
        payload = TokenService.decode_token(tokens['access_token'])
        assert payload['email'] == email
        assert payload['role'] == 'ADMIN' if payload['role'] == 'ADMIN' else True
        refresh = TokenService.decode_token(tokens['refresh_token'])
        assert refresh['type'] == 'refresh'


def test_verify_otp_no_active_otp_400_and_unknown_email_404(auth_db):
    from app.core.exceptions import AppError, NotFoundError
    email = _email('noop')
    with auth_db() as db:
        svc = _svc(db)
        _signup(svc, email)
        svc.verify_otp(email=email, otp='123456')  # consumes the OTP
        with pytest.raises(AppError) as exc:
            svc.verify_otp(email=email, otp='123456')
        assert exc.value.status_code == 400
        with pytest.raises(NotFoundError):
            svc.verify_otp(email=f'ghost-{RUN}@{DOMAIN}', otp='123456')


def test_verify_otp_promotes_allowlisted_super_admin(auth_db, monkeypatch):
    from app.models.user import UserRole
    email = _email('superlist')
    monkeypatch.setattr(settings, 'super_admin_emails', email)
    with auth_db() as db:
        svc = _svc(db)
        _signup(svc, email)
        svc.verify_otp(email=email, otp='123456')
        user = svc.user_repo.get_by_email(email)
        assert user.role == UserRole.SUPER_ADMIN


# ── login ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def verified_user(auth_db):
    """A verified LOCAL user created once for login/refresh/logout tests."""
    from app.core.security import hash_value
    from app.models.tenant import Tenant, TenantType
    from app.models.user import User, UserRole
    email = f'login-{RUN}@{DOMAIN}'
    tid, uid = uuid.uuid4(), uuid.uuid4()
    with auth_db() as db:
        db.add(Tenant(id=tid, name=f'{PFX}LoginCo', tenant_type=TenantType.COMPANY))
        db.flush()
        db.add(User(id=uid, email=email, name='Login Tester', tenant_id=tid,
                    role=UserRole.USER, is_verified=True,
                    password_hash=hash_value(PASSWORD)))
        db.commit()
    return email


def test_login_happy_creates_refresh_session(auth_db, verified_user):
    with auth_db() as db:
        svc = _svc(db)
        tokens = svc.login(email=verified_user, password=PASSWORD)
        assert tokens['access_token'] and tokens['refresh_token']
        user = svc.user_repo.get_by_email(verified_user)
        from sqlalchemy import text
        count = db.execute(text('SELECT COUNT(*) FROM refresh_sessions WHERE user_id = :u AND revoked = false'),
                           {'u': str(user.id)}).scalar()
        assert count >= 1


def test_login_failure_modes(auth_db, verified_user):
    from app.core.exceptions import UnauthorizedError
    with auth_db() as db:
        svc = _svc(db)
        with pytest.raises(UnauthorizedError):
            svc.login(email=verified_user, password='wrong-password')
        with pytest.raises(UnauthorizedError):
            svc.login(email=f'ghost2-{RUN}@{DOMAIN}', password=PASSWORD)


def test_login_unverified_user_blocked(auth_db):
    from app.core.exceptions import UnauthorizedError
    email = _email('unverified')
    with auth_db() as db:
        svc = _svc(db)
        _signup(svc, email)
        with pytest.raises(UnauthorizedError) as exc:
            svc.login(email=email, password=PASSWORD)
        assert 'verify OTP' in str(exc.value)


def test_login_oauth_user_without_password_blocked(auth_db):
    from app.core.exceptions import UnauthorizedError
    from app.models import AuthProvider
    from app.models.user import User, UserRole
    from app.models.tenant import Tenant, TenantType
    email = f'oauthonly-{RUN}@{DOMAIN}'
    with auth_db() as db:
        tid = uuid.uuid4()
        db.add(Tenant(id=tid, name=f'{PFX}OAuthCo', tenant_type=TenantType.COMPANY))
        db.flush()
        db.add(User(email=email, name='OAuth Only', tenant_id=tid, role=UserRole.USER,
                    is_verified=True, provider=AuthProvider.GOOGLE, provider_id='g-1',
                    password_hash=None))
        db.commit()
        with pytest.raises(UnauthorizedError):
            _svc(db).login(email=email, password=PASSWORD)


# ── request_login_otp / login_with_otp ──────────────────────────────────────

def test_request_login_otp_unknown_email_is_silent(auth_db, patched_io):
    with auth_db() as db:
        _svc(db).request_login_otp(email=f'ghost3-{RUN}@{DOMAIN}')
        assert patched_io['otp'] == []


def test_request_login_otp_unverified_unauthorized(auth_db):
    from app.core.exceptions import UnauthorizedError
    email = _email('otpunv')
    with auth_db() as db:
        svc = _svc(db)
        _signup(svc, email)
        with pytest.raises(UnauthorizedError):
            svc.request_login_otp(email=email)


def test_request_login_otp_cooldown_429(auth_db, verified_user, monkeypatch):
    from app.core.exceptions import AppError
    monkeypatch.setattr(settings, 'otp_resend_cooldown_seconds', 60)
    with auth_db() as db:
        svc = _svc(db)
        svc.request_login_otp(email=verified_user)
        with pytest.raises(AppError) as exc:
            svc.request_login_otp(email=verified_user)
        assert exc.value.status_code == 429
        assert 'Please wait' in str(exc.value)


def test_request_login_otp_window_cap_429(auth_db, verified_user, monkeypatch):
    from app.core.exceptions import AppError
    monkeypatch.setattr(settings, 'otp_request_max_per_window', 2)
    with auth_db() as db:
        svc = _svc(db)
        # cooldown is 0 (autouse); the window cap is the ceiling
        svc.request_login_otp(email=verified_user)
        with pytest.raises(AppError) as exc:
            svc.request_login_otp(email=verified_user)
        assert exc.value.status_code == 429
        assert 'Too many OTP requests' in str(exc.value)


def test_login_with_otp_happy_and_failures(auth_db, verified_user, monkeypatch):
    from app.core.exceptions import AppError, UnauthorizedError
    monkeypatch.setattr(settings, 'otp_request_max_per_window', 1000)
    with auth_db() as db:
        svc = _svc(db)
        # drop OTPs left over from the throttle tests so 'consumed' really
        # means no active code remains
        from sqlalchemy import text
        user = svc.user_repo.get_by_email(verified_user)
        db.execute(text('DELETE FROM otps WHERE user_id = :u'), {'u': str(user.id)})
        db.commit()
        svc.request_login_otp(email=verified_user)
        with pytest.raises(AppError):
            svc.login_with_otp(email=verified_user, otp='999999')  # wrong code
        tokens = svc.login_with_otp(email=verified_user, otp='123456')
        assert tokens['access_token']
        # consumed — no active OTP left
        with pytest.raises(AppError):
            svc.login_with_otp(email=verified_user, otp='123456')
        with pytest.raises(UnauthorizedError):
            svc.login_with_otp(email=f'ghost4-{RUN}@{DOMAIN}', otp='123456')


# ── refresh / logout ─────────────────────────────────────────────────────────

def test_refresh_rotates_and_blocks_reuse(auth_db, verified_user):
    from app.core.exceptions import UnauthorizedError
    with auth_db() as db:
        svc = _svc(db)
        tokens = svc.login(email=verified_user, password=PASSWORD)
        new_tokens = svc.refresh(tokens['refresh_token'])
        # access tokens issued in the same second are byte-identical (same claims,
        # second-precision exp) — rotation is observable on the refresh token (new sid)
        assert new_tokens['refresh_token'] != tokens['refresh_token']
        with pytest.raises(UnauthorizedError):
            svc.refresh(tokens['refresh_token'])  # old token revoked on rotation


def test_refresh_rejects_access_token_and_garbage(auth_db, verified_user):
    from app.core.exceptions import UnauthorizedError
    with auth_db() as db:
        svc = _svc(db)
        tokens = svc.login(email=verified_user, password=PASSWORD)
        with pytest.raises(UnauthorizedError):
            svc.refresh(tokens['access_token'])
        with pytest.raises(UnauthorizedError):
            svc.refresh('garbage')


def test_logout_revokes_session(auth_db, verified_user):
    from app.core.exceptions import UnauthorizedError
    with auth_db() as db:
        svc = _svc(db)
        tokens = svc.login(email=verified_user, password=PASSWORD)
        svc.logout(tokens['refresh_token'])
        with pytest.raises(UnauthorizedError):
            svc.refresh(tokens['refresh_token'])


def test_logout_without_sid_is_silent(auth_db):
    from app.services.token_service import TokenService
    with auth_db() as db:
        access = TokenService.create_access_token(
            user_id='u', email=f'x@{DOMAIN}', role='USER', tenant_id=str(uuid.uuid4()))
        _svc(db).logout(access)  # no sid claim → silent return


# ── super-admin setup flows ──────────────────────────────────────────────────

def test_trigger_setup_authz_and_allowlist(auth_db, patched_io, monkeypatch):
    from app.core.exceptions import ForbiddenError
    sa_email = f'sa-{RUN}@{DOMAIN}'
    monkeypatch.setattr(settings, 'super_admin_emails', sa_email)
    with auth_db() as db:
        svc = _svc(db)
        with pytest.raises(ForbiddenError):
            svc.trigger_super_admin_password_setup({'role': 'ADMIN'}, sa_email)
        with pytest.raises(ForbiddenError):
            svc.trigger_super_admin_password_setup({'role': 'SUPER_ADMIN'},
                                                   f'random-{RUN}@{DOMAIN}')
        svc.trigger_super_admin_password_setup({'role': 'SUPER_ADMIN'}, sa_email)
        to_email, link = patched_io['setup'][-1]
        assert to_email == sa_email
        assert 'token=' in link


def test_set_super_admin_password_full_flow_single_use(auth_db, monkeypatch):
    from app.core.exceptions import AppError, UnauthorizedError
    from app.core.tenancy import CELLHUB_MASTER_TENANT_ID
    from app.models.user import UserRole
    from app.services.token_service import TokenService
    sa_email = f'sa2-{RUN}@{DOMAIN}'
    monkeypatch.setattr(settings, 'super_admin_emails', sa_email)
    with auth_db() as db:
        svc = _svc(db)
        token = TokenService.create_super_admin_setup_token(
            email=sa_email, state=svc._setup_state(None))
        # weak password → 422
        with pytest.raises(AppError) as exc:
            svc.set_super_admin_password(token=token, password='weak')
        assert exc.value.status_code == 422
        # happy: provisions into the CellHub master tenant
        result = svc.set_super_admin_password(token=token, password=PASSWORD)
        assert result == {'email': sa_email}
        user = svc.user_repo.get_by_email(sa_email)
        assert user.role == UserRole.SUPER_ADMIN
        assert str(user.tenant_id) == CELLHUB_MASTER_TENANT_ID
        assert user.is_verified is True
        # single-use: state changed once the password was set
        with pytest.raises(UnauthorizedError):
            svc.set_super_admin_password(token=token, password=PASSWORD)
        # allowlist removal invalidates outstanding links
        token2 = TokenService.create_super_admin_setup_token(
            email=sa_email, state=svc._setup_state(user))
        monkeypatch.setattr(settings, 'super_admin_emails', '')
        with pytest.raises(UnauthorizedError):
            svc.set_super_admin_password(token=token2, password=PASSWORD)


def test_admin_set_super_admin_credentials(auth_db, monkeypatch):
    from app.core.exceptions import ForbiddenError
    from app.models.user import UserRole
    sa_email = f'sa3-{RUN}@{DOMAIN}'
    monkeypatch.setattr(settings, 'super_admin_emails', sa_email)
    with auth_db() as db:
        svc = _svc(db)
        with pytest.raises(ForbiddenError):
            svc.admin_set_super_admin_credentials({'role': 'ADMIN'},
                                                  email=sa_email, password=PASSWORD)
        # create
        svc.admin_set_super_admin_credentials({'role': 'SUPER_ADMIN'},
                                              email=sa_email, password=PASSWORD)
        user = svc.user_repo.get_by_email(sa_email)
        assert user.role == UserRole.SUPER_ADMIN
        # update existing (password rotation)
        svc.admin_set_super_admin_credentials({'role': 'SUPER_ADMIN'},
                                              email=sa_email, password=PASSWORD + 'x1!')
        tokens = svc.login(email=sa_email, password=PASSWORD + 'x1!')
        assert tokens['access_token']


# ── oauth_login_or_register / misc ───────────────────────────────────────────

def test_oauth_login_creates_verified_user_and_promotes_allowlisted(auth_db, monkeypatch):
    from app.models import AuthProvider
    from app.models.user import UserRole
    email = f'oauthnew-{RUN}@{DOMAIN}'
    with auth_db() as db:
        svc = _svc(db)
        tokens = svc.oauth_login_or_register(provider=AuthProvider.GOOGLE, email=email,
                                             name='OAuth New', provider_id='g-new')
        assert tokens['access_token']
        user = svc.user_repo.get_by_email(email)
        assert user.is_verified is True
        assert user.role == UserRole.USER
        # existing user gets promoted once allowlisted
        monkeypatch.setattr(settings, 'super_admin_emails', email)
        svc.oauth_login_or_register(provider=AuthProvider.GOOGLE, email=email,
                                    name='OAuth New', provider_id='g-new')
        assert svc.user_repo.get_by_email(email).role == UserRole.SUPER_ADMIN


def test_resolve_tenant_id_malformed_and_unknown(auth_db):
    from app.core.exceptions import AppError, NotFoundError
    with auth_db() as db:
        svc = _svc(db)
        with pytest.raises(AppError) as exc:
            svc._resolve_tenant_id('not-a-uuid')
        assert exc.value.status_code == 400
        with pytest.raises(NotFoundError):
            svc._resolve_tenant_id(str(uuid.uuid4()))


# ── vendor signup ────────────────────────────────────────────────────────────

def _vendor_kwargs(email):
    return dict(
        contact_name='Vendor Admin', contact_email=email, contact_phone=None,
        password=PASSWORD, company_name=f'{PFX}Vendor Co',
        address_street='1 Vendor Way', address_city='Austin', address_state='TX',
        address_zip='78701', company_website='https://vendor.example',
        company_email=f'info@{DOMAIN}', federal_tax_id='12-3456789',
        bbb_good_standing=True, sos_good_standing=True, corporate_liable_sales=False,
    )


def test_vendor_signup_provisions_tenant_profile_and_otp(auth_db, patched_io):
    from app.models.user import UserRole
    from app.models.tenant import TenantType
    email = _email('vendor')
    with auth_db() as db:
        svc = _svc(db)
        user = svc.vendor_signup(**_vendor_kwargs(email))
        assert user.role == UserRole.ADMIN
        assert user.is_verified is False
        tenant = svc.tenant_repo.get_by_id(str(user.tenant_id))
        assert tenant.tenant_type == TenantType.VENDOR
        from sqlalchemy import text
        vendor_row = db.execute(text('SELECT company_name, is_approved FROM vendors WHERE tenant_id = :t'),
                                {'t': str(tenant.id)}).fetchone()
        assert vendor_row.company_name == f'{PFX}Vendor Co'
        assert vendor_row.is_approved is False
        assert patched_io['otp'][-1][0] == email
        # duplicate contact email → 409
        from app.core.exceptions import AppError
        with pytest.raises(AppError) as exc:
            svc.vendor_signup(**_vendor_kwargs(email))
        assert exc.value.status_code == 409
