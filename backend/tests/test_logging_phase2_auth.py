"""Phase 2 audit events from AuthService (docs/LOGGING_PLAN.md §6 Auth rows).

Service-level tests with stubbed repos — they verify that each auth outcome
emits the right MSGID/severity/fields, not the auth logic itself."""
import logging
import uuid
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError, UnauthorizedError
from app.core.logging_config import NOTICE, SD_ID_AUDIT
from app.core.security import hash_value
from app.models import AuthProvider, UserRole
from app.services.auth_service import AuthService
from app.services.otp_service import OTPService


@pytest.fixture
def captured():
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    target = logging.getLogger('secureoffice.audit')
    target.addHandler(handler)
    target.setLevel(logging.INFO)
    target.propagate = False
    yield records
    target.removeHandler(handler)


class FakeDB:
    def commit(self):
        pass

    def flush(self):
        pass


def make_service(**repo_overrides):
    service = AuthService(db=FakeDB())
    for name, stub in repo_overrides.items():
        setattr(service, name, stub)
    return service


def make_user(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        email='someone@example.com',
        password_hash=hash_value('Correct-horse-1!'),
        provider=AuthProvider.LOCAL,
        is_verified=True,
        role=UserRole.USER,
        tenant_id=uuid.uuid4(),
        tenant=None,
        permissions=['catalog.view'],
        user_type=SimpleNamespace(value='COMPANY'),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def sd(record):
    return record.sd[SD_ID_AUDIT]


class TestLoginEvents:
    def test_unknown_user_emits_login_failed(self, captured):
        service = make_service(user_repo=SimpleNamespace(get_by_email=lambda e: None))
        with pytest.raises(UnauthorizedError):
            service.login(email='ghost@example.com', password='x')
        assert [r.msgid for r in captured] == ['user_login_failed']
        record = captured[0]
        assert record.levelno == logging.WARNING
        assert sd(record)['reason'] == 'unknown_user_or_wrong_provider'
        assert sd(record)['email_attempted'] == 'ghost@example.com'

    def test_bad_password_emits_login_failed(self, captured):
        user = make_user()
        service = make_service(user_repo=SimpleNamespace(get_by_email=lambda e: user))
        with pytest.raises(UnauthorizedError):
            service.login(email=user.email, password='wrong')
        assert sd(captured[0])['reason'] == 'bad_password'
        assert sd(captured[0])['user_id'] == str(user.id)

    def test_success_emits_user_login_notice(self, captured, monkeypatch):
        user = make_user()
        service = make_service(user_repo=SimpleNamespace(get_by_email=lambda e: user))
        monkeypatch.setattr(service, '_issue_tokens_for_user', lambda u: {'access_token': 'a'})
        service.login(email=user.email, password='Correct-horse-1!')
        assert [r.msgid for r in captured] == ['user_login']
        record = captured[0]
        assert record.levelno == NOTICE
        assert sd(record)['method'] == 'password'
        assert sd(record)['actor_role'] == 'USER'
        assert sd(record)['tenant_id'] == str(user.tenant_id)


class TestOtpEvents:
    def test_wrong_otp_emits_verify_failed_with_attempts(self, captured):
        user = make_user()
        latest = SimpleNamespace(code_hash=OTPService.hash_otp('123456'))
        service = make_service(otp_repo=SimpleNamespace(decrement_attempts=lambda o: 2))
        with pytest.raises(AppError):
            service._verify_otp_attempt(latest, '999999', user=user)
        record = captured[0]
        assert record.msgid == 'otp_verify_failed'
        assert record.levelno == logging.WARNING
        assert sd(record)['attempts_remaining'] == 2
        assert sd(record)['locked'] is False

    def test_unknown_email_otp_request_logged_as_skipped(self, captured):
        service = make_service(user_repo=SimpleNamespace(get_by_email=lambda e: None))
        service.request_login_otp(email='probe@example.com')
        record = captured[0]
        assert record.msgid == 'otp_requested'
        assert sd(record)['status'] == 'skipped'
        assert sd(record)['reason'] == 'unknown_email'


class TestSessionEvents:
    def test_logout_emits_user_logout(self, captured, monkeypatch):
        from app.services import auth_service as mod
        session = SimpleNamespace(user_id=uuid.uuid4())
        monkeypatch.setattr(mod.TokenService, 'decode_token', staticmethod(lambda t: {'sid': 5}))
        service = make_service(refresh_repo=SimpleNamespace(
            get_active_by_id=lambda sid: session, revoke=lambda s: None,
        ))
        service.logout('some-refresh-token')
        assert [r.msgid for r in captured] == ['user_logout']
        assert sd(captured[0])['user_id'] == str(session.user_id)

    def test_oauth_existing_user_emits_oauth_login(self, captured, monkeypatch):
        user = make_user(provider=AuthProvider.GOOGLE)
        service = make_service(user_repo=SimpleNamespace(get_by_email=lambda e: user))
        monkeypatch.setattr(service, '_issue_tokens_for_user', lambda u: {'access_token': 'a'})
        service.oauth_login_or_register(
            provider=AuthProvider.GOOGLE, email=user.email, name='X', provider_id='sub1',
        )
        record = captured[0]
        assert record.msgid == 'oauth_login'
        assert sd(record)['provider'] == AuthProvider.GOOGLE.value
        assert sd(record)['new_user_created'] is False


class TestSuperAdminEvents:
    def test_admin_set_credentials_emits_event(self, captured, monkeypatch):
        from app.services import auth_service as mod
        target = make_user(email='teammate@cellhubms.com', role=UserRole.SUPER_ADMIN)
        monkeypatch.setattr(mod.settings, 'super_admin_emails', 'teammate@cellhubms.com')
        service = make_service()
        monkeypatch.setattr(service, '_provision_super_admin', lambda e, p: target)
        actor = {'role': UserRole.SUPER_ADMIN.value, 'user_id': 'admin-1'}
        service.admin_set_super_admin_credentials(
            actor, email='teammate@cellhubms.com', password='Str0ng!Passw0rd#2026',
        )
        record = captured[0]
        assert record.msgid == 'super_admin_credentials_changed'
        assert record.levelno == NOTICE
        assert sd(record)['flow'] == 'admin_set'
        assert sd(record)['target_email'] == 'teammate@cellhubms.com'
        # the password kwarg must never appear in structured data
        assert 'password' not in sd(record)
