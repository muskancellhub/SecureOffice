"""BUG-MS-001 — deactivating a managed service must return 200, not 404.

The admin update path rebuilds its response via get_item_by_id() after setting
is_active=False; that lookup must not reject the just-deactivated item.
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError
from app.services import catalog_service as cs
from app.services.catalog_service import CatalogService


class _FakeDB:
    pass


def _service_with_product(monkeypatch, product):
    monkeypatch.setattr(cs, 'find_product_by_id_or_legacy', lambda db, item_id: product)
    svc = CatalogService(_FakeDB())
    monkeypatch.setattr(svc, '_entries_for_products', lambda products, tenant_id=None: ['ENTRY'])
    return svc


def test_inactive_item_rejected_by_default(monkeypatch):
    product = SimpleNamespace(id='svc-1', is_active=False, components=[])
    svc = _service_with_product(monkeypatch, product)
    with pytest.raises(NotFoundError):
        svc.get_item_by_id('svc-1')


def test_inactive_item_returned_with_include_inactive(monkeypatch):
    # The fix: admin write paths build a response for a just-deactivated item.
    product = SimpleNamespace(id='svc-1', is_active=False, components=[])
    svc = _service_with_product(monkeypatch, product)
    assert svc.get_item_by_id('svc-1', include_inactive=True) == 'ENTRY'


def test_active_item_unaffected(monkeypatch):
    product = SimpleNamespace(id='svc-1', is_active=True, components=[])
    svc = _service_with_product(monkeypatch, product)
    assert svc.get_item_by_id('svc-1') == 'ENTRY'
