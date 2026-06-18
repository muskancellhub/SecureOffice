"""BUG-CART-001 / TC0320 — the standalone service-add path must not crash when
a component's component_type is a plain string (not the ComponentType enum)."""

from app.models.product import ComponentType
from app.services.cart_service import REQUIRES_DEVICE_TYPES, _enum_str


def test_enum_str_handles_enum_string_and_none():
    assert _enum_str(ComponentType.SIM) == ComponentType.SIM.value
    # The fix: a raw string (SERVICE/SQLite rows) renders instead of raising.
    assert _enum_str('SIM') == 'SIM'
    assert _enum_str(None) == ''


def test_requires_device_check_works_for_string_component_type():
    # The standalone-add gate compares against ComponentType.*.value strings;
    # a raw-string component_type must still match correctly.
    assert _enum_str('SIM') in REQUIRES_DEVICE_TYPES
    assert _enum_str(ComponentType.SIM) in REQUIRES_DEVICE_TYPES
