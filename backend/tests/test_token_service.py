"""TokenService — pure JWT unit tests (no DB, real jose encoding)."""
import pytest

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.services.token_service import TokenService

settings = get_settings()


def test_access_token_roundtrip():
    token = TokenService.create_access_token(
        user_id='u1', email='a@b.co', role='ADMIN', user_type='COMPANY',
        tenant_id='t1', tenant_type='COMPANY',
    )
    payload = TokenService.decode_token(token)
    assert payload['user_id'] == 'u1'
    assert payload['email'] == 'a@b.co'
    assert payload['role'] == 'ADMIN'
    assert payload['user_type'] == 'COMPANY'
    assert payload['tenant_id'] == 't1'
    assert payload['tenant_type'] == 'COMPANY'
    assert payload['type'] == 'access'


def test_refresh_token_roundtrip():
    token = TokenService.create_refresh_token(user_id='u1', session_id=42)
    payload = TokenService.decode_token(token)
    assert payload['user_id'] == 'u1'
    assert payload['sid'] == 42
    assert payload['type'] == 'refresh'


def test_decode_garbage_token_raises():
    with pytest.raises(UnauthorizedError):
        TokenService.decode_token('not-a-jwt')


def test_decode_wrong_secret_raises():
    from jose import jwt
    forged = jwt.encode({'user_id': 'u1'}, 'some-other-secret', algorithm=settings.jwt_algorithm)
    with pytest.raises(UnauthorizedError):
        TokenService.decode_token(forged)


def test_decode_expired_token_raises(monkeypatch):
    monkeypatch.setattr(settings, 'access_token_expire_minutes', -1)
    token = TokenService.create_access_token(
        user_id='u1', email='a@b.co', role='USER', tenant_id='t1',
    )
    with pytest.raises(UnauthorizedError):
        TokenService.decode_token(token)


def test_super_admin_setup_token_roundtrip_lowercases_email():
    token = TokenService.create_super_admin_setup_token(email='  Admin@Corp.COM ', state='abc123')
    payload = TokenService.decode_super_admin_setup_token(token)
    assert payload['email'] == 'admin@corp.com'
    assert payload['state'] == 'abc123'
    assert payload['type'] == TokenService.SUPER_ADMIN_SETUP_TYPE


def test_decode_setup_token_rejects_access_token():
    access = TokenService.create_access_token(
        user_id='u1', email='a@b.co', role='USER', tenant_id='t1',
    )
    with pytest.raises(UnauthorizedError):
        TokenService.decode_super_admin_setup_token(access)
