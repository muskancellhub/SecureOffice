"""BUG-CART-003 — the cart response carries a non-blocking advisory when a line
total is unusually large (no hard cap)."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.cart import _serialize_cart


def _line(unit_price: float, quantity: int):
    return SimpleNamespace(
        id=uuid.uuid4(),
        product_id=None,
        component_id=None,
        price_snapshot={'name': 'Access Point', 'type': 'DEVICE', 'billing_cycle': 'ONE_TIME'},
        unit_price=unit_price,
        quantity=quantity,
        currency='USD',
        applies_to_line_id=None,
        created_at=datetime.now(timezone.utc),
    )


def _cart(lines):
    return SimpleNamespace(id=uuid.uuid4(), status=SimpleNamespace(value='ACTIVE'), lines=lines)


def test_high_value_line_emits_warning():
    resp = _serialize_cart(_cart([_line(391.24, 1368)]))  # ~$535K
    assert resp.warnings
    assert 'review' in resp.warnings[0].lower()


def test_normal_cart_has_no_warnings():
    resp = _serialize_cart(_cart([_line(391.24, 3)]))  # ~$1.2K
    assert resp.warnings == []


def _service_line(unit_price: float, quantity: int):
    return SimpleNamespace(
        id=uuid.uuid4(), product_id=None, component_id=None,
        price_snapshot={'name': 'Managed Router', 'type': 'SERVICE', 'billing_cycle': 'MONTHLY', 'billing': 'RECURRING'},
        unit_price=unit_price, quantity=quantity, currency='USD',
        applies_to_line_id=None, created_at=datetime.now(timezone.utc),
    )


def test_setup_included_only_with_managed_services():
    # BUG-CART-SETUP-001: derived from cart contents, not hard-coded.
    assert _serialize_cart(_cart([_line(391.24, 3)])).setup_included is False  # hardware only
    assert _serialize_cart(_cart([_service_line(29.0, 2)])).setup_included is True  # has service


def test_repriced_line_emits_warning():
    # BUG-BOM-CART-PRICE-001: a line flagged price_changed surfaces a notice.
    line = _line(391.24, 3)
    line.price_snapshot = {**line.price_snapshot, 'price_changed': True, 'source_bom_unit_price': 375.0}
    resp = _serialize_cart(_cart([line]))
    assert any('repriced' in w.lower() for w in resp.warnings)
