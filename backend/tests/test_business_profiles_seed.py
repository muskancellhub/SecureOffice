"""Guards against drift between the workbook, the committed seed JSON, and the
guardrail allow-list.

- The committed ``business_profiles.json`` must byte-match a fresh conversion of
  ``business_requirements.xlsx`` (so the two can never silently diverge).
- ``ALLOWED_BUSINESS_TYPES`` in the guardrail policy must equal the seed's
  ``businessTypes`` (so the closed pick-list stays in sync).
- The loader derivations must be coherent for every seed type.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.core.guardrail_policy import ALLOWED_BUSINESS_TYPES
from app.services import business_profiles as bp

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_JSON_PATH = _BACKEND_ROOT / "app" / "data" / "business_profiles" / "business_profiles.json"
_SCRIPT_PATH = _BACKEND_ROOT / "scripts" / "build_business_profiles.py"


def _load_build_module():
    spec = importlib.util.spec_from_file_location("build_business_profiles", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_seed_matches_fresh_conversion():
    """Re-run the xlsx→json converter and assert the committed JSON matches.

    Skips (does not fail) if openpyxl or the workbook is unavailable in the
    environment, so CI without the binary dependency still runs the rest.
    """
    if not _SCRIPT_PATH.exists():
        pytest.skip("converter script not present")
    try:
        build_module = _load_build_module()
    except ImportError:
        pytest.skip("openpyxl not installed")
    if not build_module.XLSX_PATH.exists():
        pytest.skip("source workbook not present")

    fresh = build_module.build()
    committed = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    assert fresh == committed, (
        "business_profiles.json is stale — re-run "
        "`python backend/scripts/build_business_profiles.py` and commit the result."
    )


def test_allowed_business_types_match_seed():
    assert set(ALLOWED_BUSINESS_TYPES) == set(bp.list_business_types())
    assert len(bp.list_business_types()) == 8


def test_loader_derivations_are_coherent_for_all_types():
    for business_type in bp.list_business_types():
        profile = bp.get_profile(business_type)

        load = bp.aggregate_device_load(profile)
        assert load["totalDevices"] >= 0
        assert sum(load["byCategory"].values()) == load["totalDevices"]

        posture = bp.derive_posture(profile)
        assert set(posture) == {
            "needsCellularBackup",
            "redundancyEnabled",
            "needsManagedServices",
            "needsGuestVlan",
            "needsCameraVlan",
            "needsPaymentVlan",
        }
        assert all(isinstance(v, bool) for v in posture.values())


def test_unknown_business_type_raises():
    with pytest.raises(bp.UnknownBusinessTypeError):
        bp.get_profile("Spaceport")
