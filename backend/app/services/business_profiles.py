"""Loader + derivations for the business-requirements seed.

The seed (``app/data/business_profiles/business_profiles.json``, generated from
``business_requirements.xlsx`` by ``scripts/build_business_profiles.py``) is the
per-business-type default matrix that makes the network design business-aware:
8 types x ~54 requirement attributes. See ``docs/plans/ai-design-generation/``.

This module is the deterministic consumer of that seed (Section 6.0 of the plan):
- ``get_profile`` / ``list_business_types`` — raw access (also feeds the AI
  ``BusinessProfileKnowledgeTool``).
- ``default_field`` — seed fallback for a blank user field.
- ``aggregate_device_load`` — sums the endpoint + IoT inventory into the device
  load that drives the capacity model (the cross-type differentiation driver:
  a QSR's POS+KDS+kiosks+signage load >> a convenience store's).
- ``derive_posture`` — maps seed attributes to engineering flags (cellular
  failover, redundancy, managed services, guest/camera/payment VLAN need).

Pure data + pure functions, no DB or network. The JSON is loaded once and cached
at module import.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SEED_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "business_profiles"
    / "business_profiles.json"
)

# ---------------------------------------------------------------------------
# Device inventory groupings — which seed attributes count as deployed devices
# and how they roll up. The capacity model only cares about the total; the
# per-category breakdown is surfaced for the rationale / topology signals.
# ---------------------------------------------------------------------------
DEVICE_CATEGORIES: dict[str, tuple[str, ...]] = {
    "staffEndpoints": (
        "Laptops",
        "Desktop computers",
        "Tablets",
        "Mobile phones",
    ),
    "posCommerce": (
        "POS terminals",
        "Handheld POS devices",
        "Self-checkout machines",
        "Barcode scanners",
        "Receipt printers",
        "Label printers",
    ),
    "surveillance": (
        "Number of IP cameras",
    ),
    "customerExperience": (
        "Digital signage screens",
        "Self-order kiosks",
        "Customer tablets",
        "Music / audio streaming systems",
    ),
    "restaurant": (
        "Kitchen display systems",
        "Online ordering tablets",
        "Drive-thru systems",
    ),
    "iotSmart": (
        "Smart refrigerators",
        "Smart coffee machines",
        "Vending machines",
        "Lighting controllers",
        "Sensors",
        "Inventory scanners",
        "Facility management systems",
    ),
    "automation": (
        "Delivery robots",
        "Inventory robots",
        "Smart shelves",
        "RFID gates",
    ),
}

# Payment-bearing attributes (drive the payment VLAN signal).
_PAYMENT_ATTRS = ("POS terminals", "Handheld POS devices", "Self-checkout machines")


class UnknownBusinessTypeError(KeyError):
    """Raised when a business type is not one of the 8 seed types."""


@lru_cache(maxsize=1)
def _load_seed() -> dict[str, Any]:
    with _SEED_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def list_business_types() -> list[str]:
    """The closed pick-list of 8 business types, in seed order."""
    return list(_load_seed().get("businessTypes", []))


def list_attributes() -> list[str]:
    return list(_load_seed().get("attributes", []))


def get_profile(business_type: str) -> dict[str, Any]:
    """Return the full per-type default profile. Raises for unknown types."""
    profiles = _load_seed().get("profiles", {})
    if business_type not in profiles:
        raise UnknownBusinessTypeError(business_type)
    return profiles[business_type]


def default_field(business_type: str, attribute: str) -> Any:
    """Seed fallback for a single attribute; None if the type/attribute is
    absent so callers can decide their own default."""
    try:
        return get_profile(business_type).get(attribute)
    except UnknownBusinessTypeError:
        return None


# ---------------------------------------------------------------------------
# Coercion helpers — the seed mixes ints, bools, and the occasional "Yes"/"No"
# or comma-joined list. Be liberal in what we accept.
# ---------------------------------------------------------------------------

def _as_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return 0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value.strip().lower() in {"yes", "true", "y", "1"}
    if isinstance(value, list):
        return len(value) > 0
    return False


def aggregate_device_load(profile: dict[str, Any]) -> dict[str, Any]:
    """Sum the device inventory into the load that feeds the capacity model.

    Returns ``{"totalDevices": int, "byCategory": {category: int}}``. Guest
    Wi-Fi users are intentionally excluded — they are wireless *clients* (handled
    via user count), not deployed devices.
    """
    by_category: dict[str, int] = {}
    total = 0
    for category, attrs in DEVICE_CATEGORIES.items():
        subtotal = sum(_as_count(profile.get(attr)) for attr in attrs)
        by_category[category] = subtotal
        total += subtotal
    return {"totalDevices": total, "byCategory": by_category}


def derive_posture(profile: dict[str, Any]) -> dict[str, bool]:
    """Map seed attributes to engineering flags used by the calculator input,
    the BOM service, and topology segmentation."""
    payment_devices = sum(_as_count(profile.get(a)) for a in _PAYMENT_ATTRS)
    cameras = _as_count(profile.get("Number of IP cameras"))
    ownership = str(profile.get("Network ownership") or "").lower()

    return {
        "needsCellularBackup": _truthy(profile.get("Need backup internet?")),
        "redundancyEnabled": _truthy(profile.get("Need redundancy?")),
        "needsManagedServices": "managed" in ownership,
        "needsGuestVlan": _truthy(profile.get("Guest Wi-Fi required?")),
        "needsCameraVlan": cameras > 0 or _truthy(profile.get("NVR / DVR system present")),
        "needsPaymentVlan": payment_devices > 0 or _truthy(profile.get("Square POS")),
    }
