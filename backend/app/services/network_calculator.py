"""Python port of the deterministic network design calculator.

This is a faithful, numerically-identical port of the TypeScript engine in
``frontend/src/calculator/`` (``calculator.ts`` + ``constants.ts`` +
``validation.ts``). It is the **physics/capacity floor** the AI design layer is
clamped to (see ``docs/plans/ai-design-generation/``). Keeping it server-side
lets the AI flow run end-to-end in the backend and lets the validator re-run the
math independently of the client.

Invariants that must be preserved against the TS source:
- the result dict uses the SAME camelCase keys as ``NetworkCalculatorResult`` so
  it drops straight into the existing JSONB contract and is consumed unchanged by
  ``network_bom_service`` / ``network_topology_service`` and the frontend.
- ``round2`` mirrors JS ``Math.round((v + Number.EPSILON) * 100) / 100``.

Parity is asserted by ``backend/tests/test_network_calculator_parity.py`` against
the golden fixtures in ``frontend/src/calculator/__tests__``.
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Constants (mirror of constants.ts)
# ---------------------------------------------------------------------------

OBSTRUCTION_LOSS_DB: dict[str, float] = {
    "open": 0,
    "standard": 6,
    "dense": 12,
    "very_dense": 20,
}

WIFI_STANDARD_THROUGHPUT_MBPS: dict[str, float] = {
    "wifi5": 400,
    "wifi6": 600,
    "wifi6e": 900,
    "wifi7": 1200,
}

ENVIRONMENT_CONCURRENCY_FACTOR: dict[str, float] = {
    "office": 0.6,
    "hospital": 0.7,
    "warehouse": 0.4,
    "stadium": 0.8,
}

DEFAULT_CONCURRENCY_FACTOR = 0.6
DEFAULT_SWITCH_PORTS = 24

DEFAULT_OPTIONAL_OVERRIDES: dict[str, float] = {
    "concurrencyFactor": DEFAULT_CONCURRENCY_FACTOR,
    "txPowerDbm": 18,
    "txGainDbi": 4,
    "targetRssiDbm": -67,
    "fadeMarginDb": 10,
    "cableLossDb": 2,
    "floorLossDb": 0,
    "packingEfficiency": 0.75,
    "airtimeEfficiency": 0.55,
    "channelReuse": 0.8,
    "overheadFactor": 1.3,
    "redundancyFactor": 1.25,
    "frequencyMHz": 5000,
}

INDOOR_RADIUS_FT_MIN = 10
INDOOR_RADIUS_FT_MAX = 200
FEET_PER_KM = 3280.84
FSPL_CONSTANT_DB = 32.44

# JS Number.EPSILON — included in round2 to match the TS rounding nudge exactly.
_EPSILON = 2.220446049250313e-16

ENVIRONMENT_TYPES = ("office", "hospital", "warehouse", "stadium", "custom")
OBSTRUCTION_TYPES = ("open", "standard", "dense", "very_dense")
WIFI_STANDARDS = ("wifi5", "wifi6", "wifi6e", "wifi7")

PRICING_FIELDS = (
    "indoorAPPrice",
    "licensePrice",
    "cablingCostPerDrop",
    "laborHoursPerAP",
    "laborRate",
    "switchPrice",
    "upsPrice",
    "markupPct",
    "taxPct",
)


class CalculatorError(ValueError):
    """Raised when calculator input fails validation (mirrors TS throws)."""


def round2(value: float) -> float:
    """Round to 2 decimals matching JS ``Math.round((v + EPSILON) * 100) / 100``.

    All values produced here are non-negative, so ``floor(x + 0.5)`` reproduces
    ``Math.round`` (round-half-up toward +Infinity) without Python's
    banker's-rounding divergence.
    """
    return math.floor((value + _EPSILON) * 100 + 0.5) / 100.0


# ---------------------------------------------------------------------------
# Validation (mirror of validation.ts)
# ---------------------------------------------------------------------------

def _assert_finite(
    value: Any,
    field_name: str,
    *,
    minimum: float | None = None,
    greater_than_zero: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalculatorError(f"Invalid {field_name}: must be a finite number.")
    if math.isnan(value) or math.isinf(value):
        raise CalculatorError(f"Invalid {field_name}: must be a finite number.")
    if greater_than_zero and value <= 0:
        raise CalculatorError(f"Invalid {field_name}: must be greater than 0.")
    if minimum is not None and value < minimum:
        raise CalculatorError(f"Invalid {field_name}: must be >= {minimum}.")
    return float(value)


def _assert_enum(value: Any, allowed: tuple[str, ...], field_name: str) -> str:
    if value not in allowed:
        raise CalculatorError(
            f"Invalid {field_name}: '{value}'. Allowed values are: {', '.join(allowed)}."
        )
    return value


def _validate_pricing(pricing: dict[str, Any]) -> dict[str, float]:
    if not isinstance(pricing, dict):
        raise CalculatorError("Invalid pricing: object required.")
    return {
        field: _assert_finite(pricing.get(field), f"pricing.{field}", minimum=0)
        for field in PRICING_FIELDS
    }


def _validate_overrides(overrides: dict[str, Any] | None) -> dict[str, float]:
    merged = {**DEFAULT_OPTIONAL_OVERRIDES, **(overrides or {})}
    return {
        "concurrencyFactor": _assert_finite(merged["concurrencyFactor"], "optionalOverrides.concurrencyFactor", minimum=0),
        "txPowerDbm": _assert_finite(merged["txPowerDbm"], "optionalOverrides.txPowerDbm"),
        "txGainDbi": _assert_finite(merged["txGainDbi"], "optionalOverrides.txGainDbi"),
        "targetRssiDbm": _assert_finite(merged["targetRssiDbm"], "optionalOverrides.targetRssiDbm"),
        "fadeMarginDb": _assert_finite(merged["fadeMarginDb"], "optionalOverrides.fadeMarginDb", minimum=0),
        "cableLossDb": _assert_finite(merged["cableLossDb"], "optionalOverrides.cableLossDb", minimum=0),
        "floorLossDb": _assert_finite(merged["floorLossDb"], "optionalOverrides.floorLossDb", minimum=0),
        "packingEfficiency": _assert_finite(merged["packingEfficiency"], "optionalOverrides.packingEfficiency", greater_than_zero=True),
        "airtimeEfficiency": _assert_finite(merged["airtimeEfficiency"], "optionalOverrides.airtimeEfficiency", greater_than_zero=True),
        "channelReuse": _assert_finite(merged["channelReuse"], "optionalOverrides.channelReuse", greater_than_zero=True),
        "overheadFactor": _assert_finite(merged["overheadFactor"], "optionalOverrides.overheadFactor", greater_than_zero=True),
        "redundancyFactor": _assert_finite(merged["redundancyFactor"], "optionalOverrides.redundancyFactor", greater_than_zero=True),
        "frequencyMHz": _assert_finite(merged["frequencyMHz"], "optionalOverrides.frequencyMHz", greater_than_zero=True),
    }


def validate_and_normalize_input(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CalculatorError("Invalid input: payload is required.")

    business_type = raw.get("businessType")
    if not isinstance(business_type, str) or not business_type.strip():
        raise CalculatorError("Invalid businessType: must be a non-empty string.")

    environment_type = _assert_enum(raw.get("environmentType"), ENVIRONMENT_TYPES, "environmentType")
    obstruction_type = _assert_enum(raw.get("obstructionType"), OBSTRUCTION_TYPES, "obstructionType")
    wifi_standard = _assert_enum(raw.get("wifiStandard"), WIFI_STANDARDS, "wifiStandard")

    number_of_floors = raw.get("numberOfFloors")
    if number_of_floors is not None:
        number_of_floors = _assert_finite(number_of_floors, "numberOfFloors", greater_than_zero=True)

    return {
        "businessType": business_type.strip(),
        "environmentType": environment_type,
        "totalFloorAreaSqft": _assert_finite(raw.get("totalFloorAreaSqft"), "totalFloorAreaSqft", greater_than_zero=True),
        "numberOfFloors": number_of_floors,
        "obstructionType": obstruction_type,
        "wifiStandard": wifi_standard,
        "totalUsers": _assert_finite(raw.get("totalUsers"), "totalUsers", greater_than_zero=True),
        "devicesPerUser": _assert_finite(raw.get("devicesPerUser"), "devicesPerUser", greater_than_zero=True),
        "throughputPerUserMbps": _assert_finite(raw.get("throughputPerUserMbps"), "throughputPerUserMbps", greater_than_zero=True),
        "redundancyEnabled": bool(raw.get("redundancyEnabled", False)),
        "switchPorts": _assert_finite(raw.get("switchPorts", DEFAULT_SWITCH_PORTS), "switchPorts", greater_than_zero=True),
        "upsRequired": bool(raw.get("upsRequired", False)),
        "pricing": _validate_pricing(raw.get("pricing")),
        "optionalOverrides": _validate_overrides(raw.get("optionalOverrides")),
    }


# ---------------------------------------------------------------------------
# Pure formula functions (mirror of calculator.ts)
# ---------------------------------------------------------------------------

def get_obstruction_loss(obstruction_type: str) -> float:
    return OBSTRUCTION_LOSS_DB[obstruction_type]


def get_standard_throughput(wifi_standard: str) -> float:
    return WIFI_STANDARD_THROUGHPUT_MBPS[wifi_standard]


def get_concurrency_factor(environment_type: str, override: float | None = None) -> float:
    if environment_type == "custom":
        return override if override is not None else DEFAULT_CONCURRENCY_FACTOR
    if override is not None:
        return override
    return ENVIRONMENT_CONCURRENCY_FACTOR[environment_type]


def calculate_indoor_allowed_path_loss(
    *,
    tx_power_dbm: float,
    tx_gain_dbi: float,
    target_rssi_dbm: float,
    obstruction_loss_db: float,
    fade_margin_db: float,
    cable_loss_db: float,
    floor_loss_db: float,
) -> float:
    return (
        tx_power_dbm
        + tx_gain_dbi
        + abs(target_rssi_dbm)
        - obstruction_loss_db
        - fade_margin_db
        - cable_loss_db
        - floor_loss_db
    )


def invert_fspl_to_distance_km(allowed_path_loss_db: float, frequency_mhz: float) -> float:
    return 10 ** ((allowed_path_loss_db - FSPL_CONSTANT_DB - 20 * math.log10(frequency_mhz)) / 20)


def convert_km_to_feet(distance_km: float) -> float:
    return distance_km * FEET_PER_KM


def clamp_indoor_radius_ft(radius_ft: float) -> float:
    return min(INDOOR_RADIUS_FT_MAX, max(INDOOR_RADIUS_FT_MIN, radius_ft))


def calculate_effective_cell_area_sqft(indoor_radius_ft: float, packing_efficiency: float) -> float:
    return math.pi * indoor_radius_ft ** 2 * packing_efficiency


def calculate_coverage_aps(total_floor_area_sqft: float, effective_cell_area_sqft: float) -> int:
    return math.ceil(total_floor_area_sqft / effective_cell_area_sqft)


def calculate_capacity_aps(
    total_users: float,
    devices_per_user: float,
    throughput_per_user_mbps: float,
    concurrency_factor: float,
    standard_throughput_mbps: float,
    airtime_efficiency: float,
    channel_reuse: float,
    overhead_factor: float,
) -> dict[str, float]:
    effective_users = total_users * concurrency_factor
    total_devices = effective_users * devices_per_user
    usable_throughput_mbps = standard_throughput_mbps * airtime_efficiency * channel_reuse
    required_throughput_mbps = total_devices * throughput_per_user_mbps * overhead_factor
    capacity_aps = math.ceil(required_throughput_mbps / usable_throughput_mbps)
    return {
        "effectiveUsers": effective_users,
        "totalDevices": total_devices,
        "usableThroughputMbps": usable_throughput_mbps,
        "requiredThroughputMbps": required_throughput_mbps,
        "capacityAPs": capacity_aps,
    }


def calculate_switch_count(total_aps: int, switch_ports: float) -> int:
    return math.ceil(total_aps / switch_ports)


def calculate_capex(
    *,
    indoor_aps_final: int,
    switch_count: int,
    ups_required: bool,
    pricing: dict[str, float],
) -> dict[str, float]:
    indoor_hardware = indoor_aps_final * pricing["indoorAPPrice"]
    licenses = indoor_aps_final * pricing["licensePrice"]
    cabling = indoor_aps_final * pricing["cablingCostPerDrop"]
    labor = indoor_aps_final * pricing["laborHoursPerAP"] * pricing["laborRate"]
    switch_cost = switch_count * pricing["switchPrice"]
    ups_cost = switch_count * pricing["upsPrice"] if ups_required else 0
    capex_base = indoor_hardware + licenses + cabling + labor + switch_cost + ups_cost
    capex_with_markup = capex_base * (1 + pricing["markupPct"] / 100)
    capex_final = capex_with_markup * (1 + pricing["taxPct"] / 100)
    return {
        "indoorHardware": round2(indoor_hardware),
        "licenses": round2(licenses),
        "cabling": round2(cabling),
        "labor": round2(labor),
        "switchCost": round2(switch_cost),
        "upsCost": round2(ups_cost),
        "capExBase": round2(capex_base),
        "capExWithMarkup": round2(capex_with_markup),
        "capExFinal": round2(capex_final),
    }


def calculate_network_estimate(raw_input: dict[str, Any]) -> dict[str, Any]:
    """Faithful port of ``calculateNetworkEstimate``. Returns the camelCase
    result dict used across the JSONB contract."""
    inputs = validate_and_normalize_input(raw_input)
    overrides = inputs["optionalOverrides"]

    obstruction_loss_db = get_obstruction_loss(inputs["obstructionType"])
    standard_throughput_mbps = get_standard_throughput(inputs["wifiStandard"])
    concurrency_factor = get_concurrency_factor(
        inputs["environmentType"],
        overrides["concurrencyFactor"] if inputs["environmentType"] == "custom" else None,
    )

    allowed_path_loss_db = calculate_indoor_allowed_path_loss(
        tx_power_dbm=overrides["txPowerDbm"],
        tx_gain_dbi=overrides["txGainDbi"],
        target_rssi_dbm=overrides["targetRssiDbm"],
        obstruction_loss_db=obstruction_loss_db,
        fade_margin_db=overrides["fadeMarginDb"],
        cable_loss_db=overrides["cableLossDb"],
        floor_loss_db=overrides["floorLossDb"],
    )

    estimated_radius_ft = clamp_indoor_radius_ft(
        convert_km_to_feet(invert_fspl_to_distance_km(allowed_path_loss_db, overrides["frequencyMHz"]))
    )

    effective_cell_area_sqft = calculate_effective_cell_area_sqft(
        estimated_radius_ft, overrides["packingEfficiency"]
    )

    coverage_aps = calculate_coverage_aps(inputs["totalFloorAreaSqft"], effective_cell_area_sqft)

    capacity = calculate_capacity_aps(
        inputs["totalUsers"],
        inputs["devicesPerUser"],
        inputs["throughputPerUserMbps"],
        concurrency_factor,
        standard_throughput_mbps,
        overrides["airtimeEfficiency"],
        overrides["channelReuse"],
        overrides["overheadFactor"],
    )

    indoor_aps = max(coverage_aps, capacity["capacityAPs"])
    indoor_aps_final = (
        math.ceil(indoor_aps * overrides["redundancyFactor"])
        if inputs["redundancyEnabled"]
        else indoor_aps
    )
    switch_count = calculate_switch_count(indoor_aps_final, inputs["switchPorts"])

    costs = calculate_capex(
        indoor_aps_final=indoor_aps_final,
        switch_count=switch_count,
        ups_required=inputs["upsRequired"],
        pricing=inputs["pricing"],
    )

    return {
        "inputsNormalized": inputs,
        "lookupsUsed": {
            "obstructionLossDb": obstruction_loss_db,
            "concurrencyFactor": concurrency_factor,
            "standardThroughputMbps": standard_throughput_mbps,
        },
        "rfModel": {
            "allowedPathLossDb": round2(allowed_path_loss_db),
            "estimatedRadiusFt": round2(estimated_radius_ft),
            "effectiveCellAreaSqft": round2(effective_cell_area_sqft),
        },
        "capacityModel": {
            "effectiveUsers": round2(capacity["effectiveUsers"]),
            "totalDevices": round2(capacity["totalDevices"]),
            "usableThroughputMbps": round2(capacity["usableThroughputMbps"]),
            "requiredThroughputMbps": round2(capacity["requiredThroughputMbps"]),
        },
        "counts": {
            "coverageAPs": coverage_aps,
            "capacityAPs": capacity["capacityAPs"],
            "indoorAPs": indoor_aps,
            "indoorAPsFinal": indoor_aps_final,
            "switchCount": switch_count,
        },
        "costs": costs,
        "summary": {
            "recommendedIndoorAPs": indoor_aps_final,
            "recommendedSwitches": switch_count,
            "estimatedCapEx": costs["capExFinal"],
        },
    }


def recompute_costs_for_counts(
    result: dict[str, Any],
    *,
    indoor_aps_final: int,
    switch_count: int,
) -> dict[str, Any]:
    """Return a copy of ``result`` with counts overridden and costs/summary
    recomputed deterministically.

    Used by the AI floor-clamp: when the AI proposal is bumped up to the
    deterministic floor (or above), the dependent cost fields must be rebuilt
    from the authoritative count — the AI never sets prices.
    """
    inputs = result["inputsNormalized"]
    costs = calculate_capex(
        indoor_aps_final=indoor_aps_final,
        switch_count=switch_count,
        ups_required=inputs["upsRequired"],
        pricing=inputs["pricing"],
    )
    new_result = {**result}
    new_result["counts"] = {
        **result["counts"],
        "indoorAPsFinal": indoor_aps_final,
        "switchCount": switch_count,
    }
    new_result["costs"] = costs
    new_result["summary"] = {
        "recommendedIndoorAPs": indoor_aps_final,
        "recommendedSwitches": switch_count,
        "estimatedCapEx": costs["capExFinal"],
    }
    return new_result
