"""OrderService — unit tests with faked repos (no DB)."""
import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models.order import OrderStatus
from app.services.order_service import OrderService


class FakeDB:
    def commit(self):
        pass


class FakeUserRepo:
    def __init__(self, known_ids):
        self.known_ids = set(known_ids)

    def get_by_id(self, user_id):
        return SimpleNamespace(id=user_id) if user_id in self.known_ids else None


class FakeOrderRepo:
    def __init__(self, orders):
        self.orders = {str(o.id): o for o in orders}
        self.calls = []

    def get_by_id(self, order_id):
        return self.orders.get(str(order_id))

    def list_for_tenant(self, tenant_id):
        self.calls.append(('tenant', tenant_id))
        return [o for o in self.orders.values() if str(o.tenant_id) == tenant_id]

    def list_for_user(self, user_id):
        self.calls.append(('user', user_id))
        return [o for o in self.orders.values() if str(o.created_by_user_id) == user_id]


TENANT_A = str(uuid.uuid4())
TENANT_B = str(uuid.uuid4())
ADMIN_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())

ADMIN = {'user_id': ADMIN_ID, 'tenant_id': TENANT_A, 'role': 'ADMIN'}
USER = {'user_id': USER_ID, 'tenant_id': TENANT_A, 'role': 'USER'}


def _order(tenant_id=TENANT_A, creator=USER_ID, status=OrderStatus.SUBMITTED):
    return SimpleNamespace(
        id=uuid.uuid4(), tenant_id=tenant_id, created_by_user_id=creator,
        status=status, estimated_delivery_date=None, confirmed_delivery_date=None,
    )


def _service(orders, known_users=(ADMIN_ID, USER_ID)):
    svc = OrderService(FakeDB())
    svc.order_repo = FakeOrderRepo(orders)
    svc.user_repo = FakeUserRepo(known_users)
    return svc


def test_list_orders_admin_routes_to_tenant_listing():
    svc = _service([_order(), _order(tenant_id=TENANT_B)])
    result = svc.list_orders(ADMIN)
    assert svc.order_repo.calls == [('tenant', TENANT_A)]
    assert all(str(o.tenant_id) == TENANT_A for o in result)


def test_list_orders_user_routes_to_user_listing():
    svc = _service([_order(creator=USER_ID), _order(creator=ADMIN_ID)])
    result = svc.list_orders(USER)
    assert svc.order_repo.calls == [('user', USER_ID)]
    assert all(str(o.created_by_user_id) == USER_ID for o in result)


def test_unknown_user_unauthorized():
    svc = _service([], known_users=())
    with pytest.raises(UnauthorizedError):
        svc.list_orders(USER)


def test_get_order_missing_not_found():
    svc = _service([])
    with pytest.raises(NotFoundError):
        svc.get_order(ADMIN, str(uuid.uuid4()))


def test_get_order_admin_cross_tenant_forbidden():
    order = _order(tenant_id=TENANT_B)
    svc = _service([order])
    with pytest.raises(ForbiddenError):
        svc.get_order(ADMIN, str(order.id))


def test_get_order_user_non_creator_forbidden_creator_allowed():
    mine, theirs = _order(creator=USER_ID), _order(creator=ADMIN_ID)
    svc = _service([mine, theirs])
    assert svc.get_order(USER, str(mine.id)) is mine
    with pytest.raises(ForbiddenError):
        svc.get_order(USER, str(theirs.id))


def test_update_order_non_admin_forbidden():
    order = _order()
    svc = _service([order])
    with pytest.raises(ForbiddenError):
        svc.update_order(USER, str(order.id), {'status': 'SHIPPED'})


def test_update_order_invalid_status_422_lists_allowed():
    order = _order()
    svc = _service([order])
    with pytest.raises(AppError) as exc:
        svc.update_order(ADMIN, str(order.id), {'status': 'NOT_A_STATUS'})
    assert exc.value.status_code == 422
    for status in OrderStatus:
        assert status.value in str(exc.value)


def test_update_order_status_change():
    order = _order(status=OrderStatus.SUBMITTED)
    svc = _service([order])
    result = svc.update_order(ADMIN, str(order.id), {'status': 'SHIPPED'})
    assert result.status == OrderStatus.SHIPPED


def test_update_order_delivery_dates():
    order = _order()
    svc = _service([order])
    est, conf = date(2026, 7, 1), date(2026, 7, 15)
    result = svc.update_order(ADMIN, str(order.id), {
        'estimated_delivery_date': est, 'confirmed_delivery_date': conf,
    })
    assert result.estimated_delivery_date == est
    assert result.confirmed_delivery_date == conf
