"""AI design generation: differentiation, floor invariant, and graceful fallback.

The LLM and the DB-backed BOM/topology services are mocked so these run in CI
without network or Postgres (plan §9.2: assert structural/directional properties
against a mocked model, not exact LLM numbers). Differentiation that comes from
the seed defaults is asserted deterministically; the AI clamp + fallback paths
are asserted with a stubbed crew.
"""

from __future__ import annotations

import pytest

from app.schemas.ai_design import AiDesignProposal, AiDesignRequest
from app.services import business_profiles as bp
from app.services import network_calculator as nc
from app.services import ai_design_service as ads
from app.services.ai_design_service import AiDesignService


# ---------------------------------------------------------------------------
# Test doubles for the DB-backed assembly services.
# ---------------------------------------------------------------------------

class _FakeBomService:
    """Records the business_context / preferences it is handed and returns a
    minimal BOM whose lines reflect the posture flags, so we can assert on what
    the orchestrator decided without touching the catalog/DB."""

    last_business_context: dict | None = None
    last_preferences: dict | None = None

    def __init__(self, *_args, **_kwargs):
        pass

    def generate_bom_from_estimate(self, *, calculator_result, business_context, preferences):
        _FakeBomService.last_business_context = business_context
        _FakeBomService.last_preferences = preferences
        counts = calculator_result["counts"]
        lines = [
            {"line_id": "line-1", "category": "wifi_ap", "name": "AP", "quantity": counts["indoorAPsFinal"], "unit_price": 850.0},
            {"line_id": "line-2", "category": "switch", "name": "Switch", "quantity": counts["switchCount"], "unit_price": 1100.0},
        ]
        if preferences.get("needsCellularBackup"):
            lines.append({"line_id": "line-3", "category": "cellular_backup", "name": "5G Backup", "quantity": 1, "unit_price": 600.0})
        if preferences.get("needsGateway"):
            lines.append({"line_id": "line-4", "category": "gateway", "name": "Gateway", "quantity": 1, "unit_price": 900.0})
        return {
            "line_items": lines,
            "subtotal": 0,
            "tax": 0,
            "grand_total": 0,
            "summary": "fake",
            "assumptions": [],
            "warnings": [],
        }


class _FakeTopologyService:
    def __init__(self, *_args, **_kwargs):
        pass

    def generate_topology_artifact_from_bom(self, *, bom, design_id=None, business_context=None):
        categories = [l.get("category") for l in bom.get("line_items") or []]
        nodes = [{"id": c, "kind": c} for c in categories]
        return {
            "topology": {"nodes": nodes, "edges": [], "metadata": {"assumptions": []}},
            "drawioXml": "<mxGraphModel></mxGraphModel>",
            "summary": {"nodeCount": len(nodes), "edgeCount": 0, "assumptions": []},
        }


@pytest.fixture(autouse=True)
def _mock_assembly(monkeypatch):
    """Swap the DB-backed services + catalog for in-memory fakes."""
    monkeypatch.setattr(ads, "NetworkBomService", _FakeBomService)
    monkeypatch.setattr(ads, "NetworkTopologyService", _FakeTopologyService)
    monkeypatch.setattr(ads, "CatalogService", lambda db: None)
    _FakeBomService.last_business_context = None
    _FakeBomService.last_preferences = None


def _stub_crew(monkeypatch, proposal):
    """Force _run_ai_crew to return a fixed proposal (or raise if it's an
    exception instance)."""
    def fake(self, **kwargs):
        if isinstance(proposal, Exception):
            raise proposal
        return proposal
    monkeypatch.setattr(AiDesignService, "_run_ai_crew", fake)


# ---------------------------------------------------------------------------
# Pure differentiation (driven by the seed, before the AI runs).
# ---------------------------------------------------------------------------

def test_qsr_vs_convenience_floor_differs_at_similar_size():
    svc = AiDesignService(None)
    qsr = bp.get_profile("Restaurant / QSR")
    conv = bp.get_profile("Convenience store")

    # The motivating bug: similar square footage, different design.
    assert abs(qsr["Average square footage"] - conv["Average square footage"]) <= 500

    qsr_floor = nc.calculate_network_estimate(
        svc._build_calculator_input(AiDesignRequest(businessType="Restaurant / QSR"), qsr)
    )
    conv_floor = nc.calculate_network_estimate(
        svc._build_calculator_input(AiDesignRequest(businessType="Convenience store"), conv)
    )

    # QSR (heavy guest Wi-Fi + device load) must size at least as high.
    assert qsr_floor["counts"]["indoorAPsFinal"] >= conv_floor["counts"]["indoorAPsFinal"]
    # And the device/guest load actually makes them different, not identical.
    assert qsr_floor["counts"]["indoorAPsFinal"] != conv_floor["counts"]["indoorAPsFinal"]

    # Posture differentiation: QSR needs guest VLAN, convenience does not.
    assert bp.derive_posture(qsr)["needsGuestVlan"] is True
    assert bp.derive_posture(conv)["needsGuestVlan"] is False


def test_warehouse_vs_office_environment_differs():
    svc = AiDesignService(None)
    wh = svc._build_calculator_input(AiDesignRequest(businessType="Warehouse"), bp.get_profile("Warehouse"))
    off = svc._build_calculator_input(AiDesignRequest(businessType="Office"), bp.get_profile("Office"))
    assert wh["environmentType"] == "warehouse"
    assert off["environmentType"] == "office"
    assert wh["obstructionType"] != off["obstructionType"]


# ---------------------------------------------------------------------------
# Floor invariant.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dpu", [0.5, 1.0, 1.5, 3.0, 8.0, 20.0])
@pytest.mark.parametrize("explicit_aps", [None, 1, 2])
def test_floor_invariant_never_below_baseline(dpu, explicit_aps):
    svc = AiDesignService(None)
    seed = bp.get_profile("Restaurant / QSR")
    base = svc._build_calculator_input(AiDesignRequest(businessType="Restaurant / QSR"), seed)
    floor = nc.calculate_network_estimate(base)

    sizing = {"devicesPerUser": dpu}
    if explicit_aps is not None:
        sizing["indoorAPsFinal"] = explicit_aps
    proposal = AiDesignProposal.model_validate({"sizing": sizing})

    result, _clamp, _warns = svc._apply_and_clamp(base_input=base, floor=floor, proposal=proposal)
    assert result["counts"]["indoorAPsFinal"] >= floor["counts"]["indoorAPsFinal"]
    assert result["counts"]["switchCount"] >= floor["counts"]["switchCount"]
    # Switch count stays consistent with the (possibly clamped) AP count.
    import math
    assert result["counts"]["switchCount"] >= math.ceil(
        result["counts"]["indoorAPsFinal"] / base["switchPorts"]
    )


# ---------------------------------------------------------------------------
# End-to-end generate() with mocked assembly + crew.
# ---------------------------------------------------------------------------

def test_generate_clamps_below_floor_proposal(monkeypatch):
    proposal = AiDesignProposal.model_validate(
        {"sizing": {"devicesPerUser": 0.5, "indoorAPsFinal": 1, "switchCount": 1},
         "rationale": {"summary": "tried to undercut"}}
    )
    _stub_crew(monkeypatch, proposal)

    out = AiDesignService(None).generate(AiDesignRequest(businessType="Restaurant / QSR"))
    assert out.ai_generated is True
    assert out.clamp_applied is True
    assert out.calculator_result["counts"]["indoorAPsFinal"] >= out.floor_snapshot["indoorAPsFinal"]
    assert any("floor" in w.lower() for w in out.warnings)


def test_generate_degrades_on_ai_failure(monkeypatch):
    _stub_crew(monkeypatch, RuntimeError("LLM timeout"))

    out = AiDesignService(None).generate(AiDesignRequest(businessType="Office"))
    assert out.ai_generated is False
    assert out.ai_model is None
    assert out.warnings  # a warning explaining the degradation
    # Still a complete, usable deterministic design.
    assert out.calculator_result["counts"]["indoorAPsFinal"] >= 1
    assert out.bom["line_items"]
    assert out.drawio_xml is not None


def test_generate_end_to_end_differentiation(monkeypatch):
    """With the deterministic path (no AI proposal), QSR and convenience still
    produce materially different designs + posture."""
    _stub_crew(monkeypatch, None)

    qsr = AiDesignService(None).generate(AiDesignRequest(businessType="Restaurant / QSR"))
    qsr_ctx = _FakeBomService.last_preferences
    conv = AiDesignService(None).generate(AiDesignRequest(businessType="Convenience store"))
    conv_prefs = _FakeBomService.last_preferences

    assert qsr.calculator_result["counts"]["indoorAPsFinal"] >= conv.calculator_result["counts"]["indoorAPsFinal"]
    assert qsr.calculator_result["counts"]["indoorAPsFinal"] != conv.calculator_result["counts"]["indoorAPsFinal"]

    # QSR guest Wi-Fi required, convenience not — visible in business_context.
    qsr_bc = _FakeBomService.last_business_context  # convenience's (last call); re-fetch per call below
    # Re-run to capture each context explicitly.
    AiDesignService(None).generate(AiDesignRequest(businessType="Restaurant / QSR"))
    assert ads.business_profiles._truthy(_FakeBomService.last_business_context["guestWifiRequired"]) is True
    AiDesignService(None).generate(AiDesignRequest(businessType="Convenience store"))
    assert ads.business_profiles._truthy(_FakeBomService.last_business_context["guestWifiRequired"]) is False

    # Both flag cellular backup (seed: both need backup internet) -> BOM line present.
    assert any(l["category"] == "cellular_backup" for l in qsr.bom["line_items"])


def test_generate_sparse_input_still_differentiates(monkeypatch):
    """Acceptance #1: differentiation holds even with only businessType set,
    because blanks fall back to the per-type seed."""
    _stub_crew(monkeypatch, None)
    qsr = AiDesignService(None).generate(AiDesignRequest(businessType="Restaurant / QSR"))
    conv = AiDesignService(None).generate(AiDesignRequest(businessType="Convenience store"))
    assert qsr.calculator_result["counts"]["indoorAPsFinal"] != conv.calculator_result["counts"]["indoorAPsFinal"]
