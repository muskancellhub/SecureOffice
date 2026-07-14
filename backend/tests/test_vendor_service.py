"""VendorService — unit tests with faked repos (no DB).

Covers the two guarantees the vendor dashboard relies on:
1. Orders are fetched by the caller's own tenant id (list_for_vendor).
2. A vendor can only open an order that actually contains one of their lines —
   otherwise it's a 404 (no IDOR into other tenants' orders).
Plus the line-projection filter that strips other vendors' lines.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.services.vendor_service import VendorService


class FakeDB:
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

    def list_for_vendor(self, vendor_tenant_id):
        self.calls.append(('vendor', vendor_tenant_id))
        return [
            o for o in self.orders.values()
            if any(str(getattr(line, 'vendor_tenant_id', None)) == vendor_tenant_id for line in o.lines)
        ]


MIX_TENANT = str(uuid.uuid4())
OTHER_VENDOR_TENANT = str(uuid.uuid4())
MIX_USER = str(uuid.uuid4())

MIX = {'user_id': MIX_USER, 'tenant_id': MIX_TENANT, 'role': 'ADMIN', 'user_type': 'VENDOR'}


def _line(vendor_tenant_id):
    return SimpleNamespace(id=uuid.uuid4(), vendor_tenant_id=vendor_tenant_id)


def _order(*line_vendor_tenants):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=str(uuid.uuid4()),  # buyer tenant, irrelevant to vendor scoping
        lines=[_line(vt) for vt in line_vendor_tenants],
    )


def _service(orders, known_users=(MIX_USER,)):
    svc = VendorService(FakeDB())
    svc.order_repo = FakeOrderRepo(orders)
    svc.user_repo = FakeUserRepo(known_users)
    return svc


def test_list_orders_routes_to_vendor_tenant():
    # An order with a MIX line and one with only another vendor's line.
    svc = _service([_order(MIX_TENANT, OTHER_VENDOR_TENANT), _order(OTHER_VENDOR_TENANT)])
    result = svc.list_orders(MIX)
    assert svc.order_repo.calls == [('vendor', MIX_TENANT)]
    assert len(result) == 1
    assert any(str(line.vendor_tenant_id) == MIX_TENANT for line in result[0].lines)


def test_unknown_user_unauthorized():
    svc = _service([], known_users=())
    with pytest.raises(UnauthorizedError):
        svc.list_orders(MIX)


def test_get_order_with_own_line_allowed():
    order = _order(MIX_TENANT, OTHER_VENDOR_TENANT)
    svc = _service([order])
    assert svc.get_order(MIX, str(order.id)) is order


def test_get_order_without_own_line_is_not_found():
    # Order exists but has no MIX line — must 404, not leak its existence.
    order = _order(OTHER_VENDOR_TENANT)
    svc = _service([order])
    with pytest.raises(NotFoundError):
        svc.get_order(MIX, str(order.id))


def test_get_order_missing_not_found():
    svc = _service([])
    with pytest.raises(NotFoundError):
        svc.get_order(MIX, str(uuid.uuid4()))


def test_vendor_lines_filters_to_caller_only():
    order = _order(MIX_TENANT, OTHER_VENDOR_TENANT, MIX_TENANT)
    lines = VendorService.vendor_lines(order, MIX_TENANT)
    assert len(lines) == 2
    assert all(str(line.vendor_tenant_id) == MIX_TENANT for line in lines)


def test_vendor_lines_ignores_unlinked_lines():
    order = _order(None, OTHER_VENDOR_TENANT)
    assert VendorService.vendor_lines(order, MIX_TENANT) == []
