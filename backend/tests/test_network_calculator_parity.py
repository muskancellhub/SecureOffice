"""Parity tests for the Python calculator port.

The golden values mirror the TS suite in
``frontend/src/calculator/__tests__/networkCalculator.test.ts``. If the TS
engine changes, both suites must be updated together — the Python port is the
backend physics floor and must stay numerically identical to the client engine.
"""

from __future__ import annotations

import pytest

from app.services.network_calculator import (
    CalculatorError,
    calculate_capacity_aps,
    calculate_capex,
    calculate_coverage_aps,
    calculate_network_estimate,
    calculate_switch_count,
    get_concurrency_factor,
    get_obstruction_loss,
    get_standard_throughput,
)

SAMPLE_INPUT = {
    "businessType": "QSR",
    "environmentType": "office",
    "totalFloorAreaSqft": 12000,
    "obstructionType": "standard",
    "wifiStandard": "wifi6",
    "totalUsers": 80,
    "devicesPerUser": 1.5,
    "throughputPerUserMbps": 4,
    "redundancyEnabled": True,
    "switchPorts": 24,
    "upsRequired": True,
    "pricing": {
        "indoorAPPrice": 850,
        "licensePrice": 120,
        "cablingCostPerDrop": 180,
        "laborHoursPerAP": 2,
        "laborRate": 95,
        "switchPrice": 1100,
        "upsPrice": 450,
        "markupPct": 15,
        "taxPct": 8.25,
    },
}


def test_lookup_functions():
    assert get_obstruction_loss("open") == 0
    assert get_obstruction_loss("dense") == 12
    assert get_standard_throughput("wifi6e") == 900
    assert get_concurrency_factor("office") == 0.6
    assert get_concurrency_factor("custom", 0.72) == 0.72
    assert get_concurrency_factor("custom") == 0.6


def test_core_count_calculations():
    assert calculate_coverage_aps(10000, 2500) == 4

    cap = calculate_capacity_aps(100, 2, 3, 0.6, 600, 0.55, 0.8, 1.3)
    assert cap["effectiveUsers"] == 60
    assert cap["totalDevices"] == 120
    assert cap["usableThroughputMbps"] == 264
    assert cap["requiredThroughputMbps"] == 468
    assert cap["capacityAPs"] == 2

    assert calculate_switch_count(25, 24) == 2


def test_capex_components():
    costs = calculate_capex(
        indoor_aps_final=3,
        switch_count=1,
        ups_required=True,
        pricing=SAMPLE_INPUT["pricing"],
    )
    assert costs == {
        "indoorHardware": 2550,
        "licenses": 360,
        "cabling": 540,
        "labor": 570,
        "switchCost": 1100,
        "upsCost": 450,
        "capExBase": 5570,
        "capExWithMarkup": 6405.5,
        "capExFinal": 6933.95,
    }


def test_validation_rejects_bad_values():
    with pytest.raises(CalculatorError, match="totalUsers"):
        calculate_network_estimate({**SAMPLE_INPUT, "totalUsers": -1})
    with pytest.raises(CalculatorError, match="environmentType"):
        calculate_network_estimate({**SAMPLE_INPUT, "environmentType": "unknown"})


def test_end_to_end_estimate():
    estimate = calculate_network_estimate(SAMPLE_INPUT)
    assert estimate["lookupsUsed"] == {
        "obstructionLossDb": 6,
        "concurrencyFactor": 0.6,
        "standardThroughputMbps": 600,
    }
    assert estimate["counts"] == {
        "coverageAPs": 2,
        "capacityAPs": 2,
        "indoorAPs": 2,
        "indoorAPsFinal": 3,
        "switchCount": 1,
    }
    assert estimate["summary"] == {
        "recommendedIndoorAPs": 3,
        "recommendedSwitches": 1,
        "estimatedCapEx": 6933.95,
    }
    assert 50 < estimate["rfModel"]["estimatedRadiusFt"] < 60


def test_redundancy_applied_only_when_enabled():
    without = calculate_network_estimate(
        {**SAMPLE_INPUT, "redundancyEnabled": False, "upsRequired": False}
    )
    assert without["counts"]["indoorAPs"] == 2
    assert without["counts"]["indoorAPsFinal"] == 2
