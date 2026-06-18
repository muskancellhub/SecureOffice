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
