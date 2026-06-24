"""Schemas for the AI-augmented network design generation endpoint.

Three shapes live here (Section 6.5 of ``docs/plans/ai-design-generation/``):

- ``AiDesignRequest`` — the enriched business profile the frontend posts. Mirrors
  the intake form keys (camelCase) so ``BusinessIntakePage`` state can be sent
  verbatim. Every field except ``businessType`` is optional/nullable — blanks
  fall back to the per-type seed, which is what keeps the design business-aware
  even with sparse input.
- ``GeneratedDesignResponse`` — the canonical artifacts in the existing JSONB
  shape plus AI metadata. The frontend persists these via the unchanged
  ``POST /designs`` path.
- ``AiDesignProposal`` — the STRICT internal schema for the LLM's raw JSON. It is
  validated/clamped before any value is trusted; the model never sets prices or
  final counts directly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.guardrail_policy import ALLOWED_BUSINESS_TYPES

# Device-count fields are whole non-negative counts. The frontend form stores
# them as strings ("", "5"); accept both and coerce to int | None. Listed by
# Python attribute name (validators bind to field names, not aliases).
_COUNT_FIELDS = (
    "locations",
    "square_footage",
    "employees",
    "peak_customers",
    "avg_daily_customers",
    "laptops",
    "desktops",
    "tablets",
    "mobile_phones",
    "pos_terminals",
    "handheld_pos_devices",
    "self_checkout_machines",
    "barcode_scanners",
    "receipt_printers",
    "label_printers",
    "ip_cameras",
    "digital_signage_screens",
    "self_order_kiosks",
    "guest_wifi_users",
    "customer_tablets",
    "music_streaming_systems",
    "kitchen_display_systems",
    "online_ordering_tablets",
    "drive_thru_systems",
    "smart_refrigerators",
    "smart_coffee_machines",
    "vending_machines",
    "lighting_controllers",
    "sensors",
    "inventory_scanners",
    "facility_management_systems",
    "delivery_robots",
    "inventory_robots",
    "smart_shelves",
    "rfid_gates",
)


class AiDesignRequest(BaseModel):
    """Enriched business profile. Field names mirror the intake form keys."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    business_type: str = Field(alias="businessType")

    # location / size / headcount / customers
    locations: int | None = None
    square_footage: int | None = Field(default=None, alias="squareFootage")
    employees: int | None = None
    peak_customers: int | None = Field(default=None, alias="peakCustomers")
    avg_daily_customers: int | None = Field(default=None, alias="avgDailyCustomers")

    # connectivity
    internet_type: str | None = Field(default=None, alias="internetType")
    primary_internet_speed: str | None = Field(default=None, alias="primaryInternetSpeed")
    needs_backup_internet: str | None = Field(default=None, alias="needsBackupInternet")
    guest_wifi_required: str | None = Field(default=None, alias="guestWifiRequired")

    # staff endpoints
    laptops: int | None = None
    desktops: int | None = None
    tablets: int | None = None
    mobile_phones: int | None = Field(default=None, alias="mobilePhones")

    # pos / commerce
    pos_terminals: int | None = Field(default=None, alias="posTerminals")
    handheld_pos_devices: int | None = Field(default=None, alias="handheldPosDevices")
    self_checkout_machines: int | None = Field(default=None, alias="selfCheckoutMachines")
    barcode_scanners: int | None = Field(default=None, alias="barcodeScanners")
    receipt_printers: int | None = Field(default=None, alias="receiptPrinters")
    label_printers: int | None = Field(default=None, alias="labelPrinters")

    # surveillance / security
    ip_cameras: int | None = Field(default=None, alias="ipCameras")
    nvr_dvr_present: str | None = Field(default=None, alias="nvrDvrPresent")
    door_access_control: str | None = Field(default=None, alias="doorAccessControl")
    alarm_system: str | None = Field(default=None, alias="alarmSystem")

    # customer experience
    digital_signage_screens: int | None = Field(default=None, alias="digitalSignageScreens")
    self_order_kiosks: int | None = Field(default=None, alias="selfOrderKiosks")
    guest_wifi_users: int | None = Field(default=None, alias="guestWifiUsers")
    customer_tablets: int | None = Field(default=None, alias="customerTablets")
    music_streaming_systems: int | None = Field(default=None, alias="musicStreamingSystems")

    # restaurant / qsr
    kitchen_display_systems: int | None = Field(default=None, alias="kitchenDisplaySystems")
    online_ordering_tablets: int | None = Field(default=None, alias="onlineOrderingTablets")
    drive_thru_systems: int | None = Field(default=None, alias="driveThruSystems")
    delivery_integration: str | None = Field(default=None, alias="deliveryIntegration")

    # iot / smart
    smart_refrigerators: int | None = Field(default=None, alias="smartRefrigerators")
    smart_coffee_machines: int | None = Field(default=None, alias="smartCoffeeMachines")
    vending_machines: int | None = Field(default=None, alias="vendingMachines")
    lighting_controllers: int | None = Field(default=None, alias="lightingControllers")
    sensors: int | None = None
    inventory_scanners: int | None = Field(default=None, alias="inventoryScanners")
    facility_management_systems: int | None = Field(default=None, alias="facilityManagementSystems")

    # automation
    delivery_robots: int | None = Field(default=None, alias="deliveryRobots")
    inventory_robots: int | None = Field(default=None, alias="inventoryRobots")
    smart_shelves: int | None = Field(default=None, alias="smartShelves")
    rfid_gates: int | None = Field(default=None, alias="rfidGates")

    # saas / ops posture
    square_pos: str | None = Field(default=None, alias="squarePos")
    odoo: str | None = None
    salesforce: str | None = None
    hubspot: str | None = None
    other_saas_tools: str | None = Field(default=None, alias="otherSaasTools")
    downtime_tolerance: str | None = Field(default=None, alias="downtimeTolerance")
    need_redundancy: str | None = Field(default=None, alias="needRedundancy")
    managed_service_preference: str | None = Field(default=None, alias="managedServicePreference")
    installation_support_needed: str | None = Field(default=None, alias="installationSupportNeeded")

    # free text — sanitized + treated as untrusted before it enters the prompt
    special_notes: str | None = Field(default=None, alias="specialNotes", max_length=4000)

    @field_validator("business_type")
    @classmethod
    def _validate_business_type(cls, value: str) -> str:
        value = (value or "").strip()
        if value not in ALLOWED_BUSINESS_TYPES:
            raise ValueError(
                f"businessType must be one of: {', '.join(sorted(ALLOWED_BUSINESS_TYPES))}"
            )
        return value

    @field_validator(*_COUNT_FIELDS, mode="before")
    @classmethod
    def _coerce_count(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            num = int(float(value))
        except (TypeError, ValueError):
            return None
        return num if num >= 0 else None


# ---------------------------------------------------------------------------
# Strict internal schema for the LLM's raw proposal (never trusted as-is).
# ---------------------------------------------------------------------------

class AiSizingProposal(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    devices_per_user: float | None = Field(default=None, alias="devicesPerUser")
    throughput_per_user_mbps: float | None = Field(default=None, alias="throughputPerUserMbps")
    concurrency_factor: float | None = Field(default=None, alias="concurrencyFactor")
    redundancy_enabled: bool | None = Field(default=None, alias="redundancyEnabled")
    needs_gateway: bool | None = Field(default=None, alias="needsGateway")
    needs_cellular_backup: bool | None = Field(default=None, alias="needsCellularBackup")
    indoor_aps_final: int | None = Field(default=None, alias="indoorAPsFinal")
    switch_count: int | None = Field(default=None, alias="switchCount")


class AiProductSelection(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    preferred_vendor: str | None = Field(default=None, alias="preferredVendor")
    prefer_cheapest: bool | None = Field(default=None, alias="preferCheapest")
    ap_item_id: str | None = Field(default=None, alias="apItemId")
    switch_item_id: str | None = Field(default=None, alias="switchItemId")
    gateway_item_id: str | None = Field(default=None, alias="gatewayItemId")
    cellular_item_id: str | None = Field(default=None, alias="cellularItemId")


class AiRationaleDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    lever: str | None = None
    change: str | None = None
    why: str | None = None


class AiRationale(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    summary: str | None = None
    decisions: list[AiRationaleDecision] = Field(default_factory=list)


class AiTopologySegment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str | None = None
    purpose: str | None = None
    device_kinds: list[str] = Field(default_factory=list, alias="deviceKinds")


class AiTopologyProposal(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    segments: list[AiTopologySegment] = Field(default_factory=list)


class AiDesignProposal(BaseModel):
    """The LLM's raw structured output. All fields optional + tolerant; the
    orchestrator validates, clamps, and grounds every value before use."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    sizing: AiSizingProposal = Field(default_factory=AiSizingProposal)
    product_selection: AiProductSelection = Field(
        default_factory=AiProductSelection, alias="productSelection"
    )
    topology: AiTopologyProposal = Field(default_factory=AiTopologyProposal)
    rationale: AiRationale = Field(default_factory=AiRationale)
    assumptions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Response.
# ---------------------------------------------------------------------------

class GeneratedDesignResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    calculator_input: dict[str, Any] = Field(alias="calculatorInput")
    calculator_result: dict[str, Any] = Field(alias="calculatorResult")
    bom: dict[str, Any]
    topology: dict[str, Any]
    drawio_xml: str | None = Field(default=None, alias="drawioXml")
    assumptions: list[str] = Field(default_factory=list)
    ai_rationale: dict[str, Any] = Field(default_factory=dict, alias="aiRationale")
    floor_snapshot: dict[str, Any] = Field(default_factory=dict, alias="floorSnapshot")
    clamp_applied: bool = Field(default=False, alias="clampApplied")
    warnings: list[str] = Field(default_factory=list)
    ai_generated: bool = Field(default=False, alias="aiGenerated")
    ai_model: str | None = Field(default=None, alias="aiModel")
    ai_prompt_version: str | None = Field(default=None, alias="aiPromptVersion")
