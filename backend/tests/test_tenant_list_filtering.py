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


def test_cart_effective_user_overrides_tenant():
    # BUG-TENANT-003: the cart routes act as the effective tenant.
    from app.routes.cart import _effective_user

    cu = {'user_id': 'u', 'tenant_id': 'home', 'role': 'SUPER_ADMIN'}
    ctx = SimpleNamespace(effective_tenant_id='company2')
    eff = _effective_user(cu, ctx)
    assert eff['tenant_id'] == 'company2'
    assert eff['user_id'] == 'u'        # other fields preserved
    assert cu['tenant_id'] == 'home'    # original not mutated


def test_users_list_scopes_to_tenant_id_not_all():
    # BUG-TENANT-008: with a tenant_id (the route defaults it to the effective
    # tenant), a SUPER_ADMIN list is scoped, not list_all() across tenants.
    import uuid
    from app.models.user import UserRole
    from app.services.user_management_service import UserManagementService

    company = str(uuid.uuid4())
    cap = {}
    svc = UserManagementService.__new__(UserManagementService)
    svc.user_repo = SimpleNamespace(
        list_by_tenant=lambda t: cap.__setitem__('by_tenant', t) or [],
        list_all=lambda: cap.__setitem__('all', True) or [],
    )
    svc._actor_role = lambda a: UserRole.SUPER_ADMIN
    svc._actor_effective_permissions = lambda a, r: set()
    svc._assert_actor_can_manage = lambda r, p: None

    svc.list_users({'tenant_id': str(uuid.uuid4()), 'role': 'SUPER_ADMIN'}, tenant_id=company)
    assert cap.get('by_tenant') == company
    assert 'all' not in cap


def test_billing_tenant_id_honors_effective_switch():
    # BUG-TENANT-004: every billing read derives its tenant from _tenant_id().
    import uuid
    from app.services.billing_service import BillingService

    home, other = uuid.uuid4(), uuid.uuid4()
    svc = BillingService.__new__(BillingService)
    cu = {'tenant_id': str(home)}
    assert str(svc._tenant_id(cu, str(other))) == str(other)   # switched
    assert str(svc._tenant_id(cu)) == str(home)                # no switch
