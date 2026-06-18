"""BUG-TENANT-001/002 — order/quote lists filter by the effective tenant
(SUPER_ADMIN switcher), not the actor's JWT home tenant."""

from types import SimpleNamespace

from app.services.order_service import OrderService
from app.services.quote_service import QuoteService

ADMIN = {'user_id': 'u', 'tenant_id': 'home', 'role': 'SUPER_ADMIN'}
USER = {'user_id': 'u', 'tenant_id': 'home', 'role': 'USER'}


def _user_repo():
    return SimpleNamespace(get_by_id=lambda uid: object())


def _order_svc(cap):
    svc = OrderService.__new__(OrderService)
    svc.user_repo = _user_repo()
    svc.order_repo = SimpleNamespace(
        list_for_tenant=lambda t: cap.__setitem__('tenant', t) or ['o'],
        list_for_user=lambda u: cap.__setitem__('user', u) or ['uo'],
    )
    return svc


def _quote_svc(cap):
    svc = QuoteService.__new__(QuoteService)
    svc.user_repo = _user_repo()
    svc.quote_repo = SimpleNamespace(
        list_for_tenant=lambda t: cap.__setitem__('tenant', t) or ['q'],
        list_for_user=lambda u: cap.__setitem__('user', u) or ['uq'],
    )
    return svc


def test_orders_admin_uses_effective_tenant():
    cap = {}
    _order_svc(cap).list_orders(ADMIN, effective_tenant_id='company2')
    assert cap['tenant'] == 'company2'


def test_orders_admin_defaults_to_home_without_switch():
    cap = {}
    _order_svc(cap).list_orders(ADMIN)
    assert cap['tenant'] == 'home'


def test_orders_non_admin_scoped_to_user_not_effective():
    cap = {}
    _order_svc(cap).list_orders(USER, effective_tenant_id='company2')
    assert cap == {'user': 'u'}  # tenant filter never used


def test_quotes_admin_uses_effective_tenant():
    cap = {}
    _quote_svc(cap).list_quotes(ADMIN, effective_tenant_id='company2')
    assert cap['tenant'] == 'company2'


def test_quotes_non_admin_scoped_to_user():
    cap = {}
    _quote_svc(cap).list_quotes(USER, effective_tenant_id='company2')
    assert cap == {'user': 'u'}
