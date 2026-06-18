"""BUG-CART-001 — catalog rendering must not crash when a SERVICE item's
billing_cycle/type is a plain string (not the BillingCycle/CatalogItemType
enum), which happens for some sources / on SQLite-backed rows."""

import pytest

from app.models.catalog import BillingCycle, CatalogItemType
from app.services.chatbot_service import _enum_value


def test_old_dot_value_access_crashes_on_plain_string():
    # The original bug: `item.billing_cycle.value` where billing_cycle is 'MONTHLY'.
    with pytest.raises(AttributeError):
        _ = 'MONTHLY'.value  # noqa: B018


def test_enum_value_handles_enum_string_and_none():
    assert _enum_value(BillingCycle.MONTHLY) == 'MONTHLY'
    assert _enum_value(CatalogItemType.SERVICE) == 'SERVICE'
    # The fix: a raw string (or None) renders instead of raising.
    assert _enum_value('MONTHLY') == 'MONTHLY'
    assert _enum_value('SERVICE') == 'SERVICE'
    assert _enum_value(None) == 'N/A'
