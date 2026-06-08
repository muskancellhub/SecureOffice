"""Multi-tenant Phase 0 — tenant-context resolution + cross-tenant authz.

Pure-logic tests (no DB): the only DB touchpoint, tenant existence, is faked so
the authorisation rules are exercised in isolation.
"""
import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.middleware import tenant_context as tc
from app.middleware.tenant_context import (
    TenantContext,
    assert_tenant_access,
    resolve_tenant_context,
)

HOME = '11111111-1111-1111-1111-111111111111'
OTHER = '22222222-2222-2222-2222-222222222222'


def _user(role='ADMIN', tenant_id=HOME):
    return {'role': role, 'tenant_id': tenant_id, 'user_id': 'u1'}


class _FakeRepo:
    def __init__(self, existing):
        self._existing = existing

    def get_by_id(self, tid):
        return object() if tid in self._existing else None


@pytest.fixture(autouse=True)
def _patch_repo(monkeypatch):
    """Make TenantRepository(db) return a fake that knows only OTHER exists."""
    monkeypatch.setattr(tc, 'TenantRepository', lambda db: _FakeRepo({OTHER}))


# ── resolve_tenant_context ──────────────────────────────────────────────────
def test_no_header_resolves_to_home():
    ctx = resolve_tenant_context(None, _user(), db=None)
    assert ctx == TenantContext(effective_tenant_id=HOME, is_cross_tenant=False)


def test_header_equal_to_home_is_not_cross_tenant():
    ctx = resolve_tenant_context(HOME, _user(), db=None)
    assert ctx.is_cross_tenant is False
    assert ctx.effective_tenant_id == HOME


def test_super_admin_can_cross_to_existing_tenant():
    ctx = resolve_tenant_context(OTHER, _user(role='SUPER_ADMIN'), db=None)
    assert ctx == TenantContext(effective_tenant_id=OTHER, is_cross_tenant=True)


def test_non_super_cross_tenant_is_forbidden():
    with pytest.raises(ForbiddenError):
        resolve_tenant_context(OTHER, _user(role='ADMIN'), db=None)


def test_super_admin_cross_to_missing_tenant_is_not_found():
    with pytest.raises(NotFoundError):
        resolve_tenant_context('33333333-3333-3333-3333-333333333333', _user(role='SUPER_ADMIN'), db=None)


# ── assert_tenant_access (closes the /pricing/customers/{tenant_id} holes) ───
def test_assert_allows_own_tenant():
    assert_tenant_access(_user(role='ADMIN'), HOME)  # no raise


def test_assert_blocks_other_tenant_for_non_super():
    with pytest.raises(ForbiddenError):
        assert_tenant_access(_user(role='ADMIN'), OTHER)


def test_assert_allows_super_admin_any_tenant():
    assert_tenant_access(_user(role='SUPER_ADMIN'), OTHER)  # no raise
