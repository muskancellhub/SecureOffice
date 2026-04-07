from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
import unittest

from app.models.catalog import BillingCycle, CatalogItemType
from app.services.catalog_service import CatalogService
from app.services.network_bom_service import NetworkBomService


@dataclass
class FakeItem:
    id: uuid.UUID
    type: CatalogItemType
    name: str
    sku: str
    vendor: str | None
    vendor_sku: str | None
    description: str | None
    price: float
    currency: str = 'USD'
    billing_cycle: BillingCycle = BillingCycle.ONE_TIME
    is_active: bool = True
    availability: str | None = 'in_stock'
    attributes: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class FakeRepo:
    def __init__(self, items: list[FakeItem]):
        self.items = items

    def list_items(self, *, item_type=None, category=None, service_kind=None, active_only=True):
        rows = list(self.items)
        if active_only:
            rows = [row for row in rows if row.is_active]
        if item_type:
            rows = [row for row in rows if row.type == item_type]
        if category:
            rows = [row for row in rows if (row.attributes or {}).get('category') == category]
        if service_kind:
            rows = [row for row in rows if (row.attributes or {}).get('service_kind') == service_kind]
        return rows

    def get_by_id(self, item_id: str):
        try:
            target = uuid.UUID(item_id)
        except Exception:
            return None
        return next((item for item in self.items if item.id == target), None)

    def get_by_sku(self, sku: str):
        return next((item for item in self.items if item.sku == sku), None)


class FakeDB:
    def commit(self):
        return None

    def refresh(self, _):
        return None


class TestUnifiedCatalogAndBom(unittest.TestCase):
    def setUp(self):
        self.items = [
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='InHand AP100',
                sku='EXCEL-inhand-ap100',
                vendor='InHand',
                vendor_sku='AP100',
                description='Wi-Fi AP',
                price=299.0,
                attributes={
                    'category': 'wifi_ap',
                    'product_type': 'wifi_ap',
                    'model': 'AP100',
                    'source_type': 'excel',
                    'source_name': 'network_vendor_catalog_public_pricing_meraki_extreme_skymirr_inhand',
                },
            ),
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='Meraki MR46',
                sku='EXCEL-meraki-mr46',
                vendor='Meraki',
                vendor_sku='MR46',
                description='Indoor Wi-Fi 6 AP',
                price=1013.0,
                attributes={
                    'category': 'wifi_ap',
                    'product_type': 'wifi_ap',
                    'model': 'MR46',
                    'source_type': 'excel',
                    'source_name': 'network_vendor_catalog_public_pricing_meraki_extreme_skymirr_inhand',
                },
            ),
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='Meraki Switch 24',
                sku='EXCEL-meraki-ms24',
                vendor='Meraki',
                vendor_sku='MS24',
                description='24-port switch',
                price=750.0,
                attributes={
                    'category': 'switch',
                    'product_type': 'switch',
                    'family_type': '24-port managed switch',
                    'source_type': 'excel',
                    'source_name': 'network_vendor_catalog_public_pricing_meraki_extreme_skymirr_inhand',
                },
            ),
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='Extreme Switch 16',
                sku='EXCEL-extreme-xs16',
                vendor='Extreme Networks',
                vendor_sku='XS16',
                description='16-port switch',
                price=420.0,
                attributes={
                    'category': 'switch',
                    'product_type': 'switch',
                    'family_type': '16-port switch',
                    'source_type': 'excel',
                    'source_name': 'network_vendor_catalog_public_pricing_meraki_extreme_skymirr_inhand',
                },
            ),
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='PAPI Laptop',
                sku='PAPI-LAPTOP-001',
                vendor='PAPI',
                vendor_sku='LAPTOP-001',
                description='Laptop',
                price=1199.0,
                attributes={
                    'category': 'laptop',
                    'product_type': 'laptop',
                    'source_type': 'paapi',
                    'source_name': 'papi_catalog',
                },
            ),
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='PAPI Phone',
                sku='PAPI-PHONE-001',
                vendor='PAPI',
                vendor_sku='PHONE-001',
                description='Phone',
                price=799.0,
                attributes={
                    'category': 'phone',
                    'product_type': 'phone',
                    'source_type': 'paapi',
                    'source_name': 'papi_catalog',
                },
            ),
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.SERVICE,
                name='Managed Router - Bronze',
                sku='MRS-BRONZE',
                vendor='Secure Office',
                vendor_sku='MRS-BRONZE',
                description='Managed service',
                price=29.0,
                billing_cycle=BillingCycle.MONTHLY,
                attributes={
                    'category': 'managed_service',
                    'product_type': 'managed_service',
                    'service_kind': 'managed_router',
                    'source_type': 'seed',
                    'source_name': 'managed_service_seed',
                },
            ),
        ]

        self.service = CatalogService(FakeDB())
        self.service.repo = FakeRepo(self.items)

    def test_unified_catalog_filters_by_source_vendor_category(self):
        all_items = self.service.list_items(item_type=None, category=None, service_kind=None)
        self.assertGreaterEqual(len(all_items), 6)

        paapi_items = self.service.list_items(
            item_type=CatalogItemType.DEVICE,
            category=None,
            service_kind=None,
            source_type='paapi',
        )
        self.assertEqual(len(paapi_items), 2)
        self.assertTrue(all(item.vendor == 'PAPI' for item in paapi_items))

        meraki_wifi = self.service.list_items(
            item_type=CatalogItemType.DEVICE,
            category='wifi_ap',
            service_kind=None,
            vendor='Meraki',
            source_type='excel',
        )
        self.assertEqual(len(meraki_wifi), 1)
        self.assertEqual(meraki_wifi[0].sku, 'EXCEL-meraki-mr46')

    def test_bom_generation_uses_excel_items_for_network_categories(self):
        result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 3, 'recommendedSwitches': 2},
                'counts': {'switchCount': 2, 'indoorAPsFinal': 3},
                'inputsNormalized': {
                    'switchPorts': 24,
                    'upsRequired': False,
                    'pricing': {
                        'licensePrice': 50,
                        'cablingCostPerDrop': 90,
                        'laborHoursPerAP': 1,
                        'laborRate': 120,
                        'taxPct': 8,
                    },
                },
            },
            preferences={},
        )

        ap_line = next(line for line in result['line_items'] if line['category'] == 'wifi_ap')
        switch_line = next(line for line in result['line_items'] if line['category'] == 'switch')

        self.assertEqual(ap_line['source_type'], 'excel')
        self.assertEqual(switch_line['source_type'], 'excel')
        self.assertEqual(ap_line['quantity'], 3)
        self.assertEqual(switch_line['quantity'], 2)
        self.assertEqual(switch_line['vendor'], 'Meraki')
        self.assertNotEqual(ap_line['vendor'], 'PAPI')

    def test_bom_preferred_vendor_and_fallback(self):
        meraki_result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 2, 'recommendedSwitches': 1},
                'counts': {'switchCount': 1, 'indoorAPsFinal': 2},
                'inputsNormalized': {'switchPorts': 24, 'pricing': {'taxPct': 0}},
            },
            preferences={'preferredVendor': 'Meraki'},
        )

        meraki_ap = next(line for line in meraki_result['line_items'] if line['category'] == 'wifi_ap')
        self.assertEqual(meraki_ap['vendor'], 'Meraki')

        fallback_result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 2, 'recommendedSwitches': 1},
                'counts': {'switchCount': 1, 'indoorAPsFinal': 2},
                'inputsNormalized': {'switchPorts': 24, 'pricing': {'taxPct': 0}},
            },
            preferences={'preferredVendor': 'SkyMirr'},
        )
        fallback_ap = next(line for line in fallback_result['line_items'] if line['category'] == 'wifi_ap')

        self.assertEqual(fallback_ap['vendor'], 'InHand')
        self.assertTrue(any('Preferred vendor SkyMirr' in note for note in fallback_result['assumptions']))

    def test_bom_includes_paapi_endpoint_devices_when_business_context_counts_present(self):
        result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 2, 'recommendedSwitches': 1},
                'counts': {'switchCount': 1, 'indoorAPsFinal': 2},
                'inputsNormalized': {'switchPorts': 24, 'pricing': {'taxPct': 0}},
            },
            business_context={
                'laptops': 8,
                'desktops': 2,
                'mobilePhones': 12,
            },
            preferences={},
        )

        laptop_line = next(line for line in result['line_items'] if line['category'] == 'laptop')
        phone_line = next(line for line in result['line_items'] if line['category'] == 'phone')

        self.assertEqual(laptop_line['source_type'], 'paapi')
        self.assertEqual(phone_line['source_type'], 'paapi')
        self.assertEqual(laptop_line['quantity'], 10)
        self.assertEqual(phone_line['quantity'], 12)

    def test_bom_prefers_paapi_endpoint_with_public_price_over_zero_price_rows(self):
        self.items.append(
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='PAPI Tablet Zero Price',
                sku='PAPI-TABLET-000',
                vendor='PAPI',
                vendor_sku='TABLET-000',
                description='Tablet with unavailable public price',
                price=0.0,
                attributes={
                    'category': 'tablet',
                    'product_type': 'tablet',
                    'source_type': 'paapi',
                    'source_name': 'papi_catalog',
                },
            )
        )
        self.items.append(
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='PAPI Tablet Priced',
                sku='PAPI-TABLET-450',
                vendor='PAPI',
                vendor_sku='TABLET-450',
                description='Tablet with public price',
                price=450.0,
                attributes={
                    'category': 'tablet',
                    'product_type': 'tablet',
                    'source_type': 'paapi',
                    'source_name': 'papi_catalog',
                },
            )
        )

        result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 2, 'recommendedSwitches': 1},
                'counts': {'switchCount': 1, 'indoorAPsFinal': 2},
                'inputsNormalized': {'switchPorts': 24, 'pricing': {}},
            },
            business_context={'tablets': 3},
            preferences={},
        )

        tablet_line = next(line for line in result['line_items'] if line['category'] == 'tablet')
        self.assertEqual(tablet_line['sku'], 'PAPI-TABLET-450')
        self.assertEqual(tablet_line['unit_price'], 450.0)

    def test_bom_adds_gateway_and_backup_devices_from_requirements(self):
        self.items.append(
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='Meraki Security Appliance',
                sku='EXCEL-MERAKI-FW-1',
                vendor='Meraki',
                vendor_sku='FW-1',
                description='Firewall / security appliance',
                price=899.0,
                attributes={
                    'category': 'firewall',
                    'product_type': 'firewall',
                    'source_type': 'excel',
                    'source_name': 'network_vendor_catalog_public_pricing_meraki_extreme_skymirr_inhand',
                },
            )
        )
        self.items.append(
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='InHand 5G Backup Gateway',
                sku='EXCEL-INHAND-CELL-1',
                vendor='InHand',
                vendor_sku='CELL-1',
                description='Cellular backup device',
                price=399.0,
                attributes={
                    'category': 'cellular_gateway',
                    'product_type': 'cellular_gateway',
                    'source_type': 'excel',
                    'source_name': 'network_vendor_catalog_public_pricing_meraki_extreme_skymirr_inhand',
                },
            )
        )

        result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 2, 'recommendedSwitches': 1},
                'counts': {'switchCount': 1, 'indoorAPsFinal': 2},
                'inputsNormalized': {'switchPorts': 24, 'pricing': {'taxPct': 0}},
            },
            business_context={
                'needRedundancy': 'Yes',
                'needsBackupInternet': 'Yes',
                'locations': 2,
            },
            preferences={},
        )

        gateway_line = next(line for line in result['line_items'] if line['category'] in {'firewall', 'gateway', 'router', 'security_appliance'})
        backup_line = next(line for line in result['line_items'] if line['category'] == 'cellular_backup')

        self.assertEqual(gateway_line['source_type'], 'excel')
        self.assertEqual(backup_line['source_type'], 'excel')
        self.assertEqual(backup_line['quantity'], 2)

    def test_bom_adds_pos_camera_and_iot_lines_from_requirement_intent(self):
        self.items.append(
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='PAPI Business Tablet',
                sku='PAPI-TABLET-200',
                vendor='PAPI',
                vendor_sku='TABLET-200',
                description='Tablet for checkout and line-busting',
                price=650.0,
                attributes={
                    'category': 'tablet',
                    'product_type': 'tablet',
                    'source_type': 'paapi',
                    'source_name': 'papi_catalog',
                },
            )
        )
        self.items.append(
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='SkyMirr Smart Camera',
                sku='EXCEL-SKYMIRR-CAM-1',
                vendor='SkyMirr',
                vendor_sku='CAM-1',
                description='IP surveillance camera',
                price=299.0,
                attributes={
                    'category': 'camera',
                    'product_type': 'camera',
                    'source_type': 'excel',
                    'source_name': 'network_vendor_catalog_public_pricing_meraki_extreme_skymirr_inhand',
                },
            )
        )
        self.items.append(
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='Extreme Occupancy Sensor',
                sku='EXCEL-EXTREME-SENSOR-1',
                vendor='Extreme Networks',
                vendor_sku='SENSOR-1',
                description='Smart occupancy sensor',
                price=89.0,
                attributes={
                    'category': 'sensor',
                    'product_type': 'sensor',
                    'source_type': 'excel',
                    'source_name': 'network_vendor_catalog_public_pricing_meraki_extreme_skymirr_inhand',
                },
            )
        )

        result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 2, 'recommendedSwitches': 1},
                'counts': {'switchCount': 1, 'indoorAPsFinal': 2},
                'inputsNormalized': {'switchPorts': 24, 'pricing': {'taxPct': 0}},
            },
            business_context={
                'posTerminals': 3,
                'handheldPosDevices': 2,
                'ipCameras': 4,
                'sensors': 5,
            },
            preferences={},
        )

        pos_line = next(line for line in result['line_items'] if line['category'] == 'pos_systems')
        camera_line = next(line for line in result['line_items'] if line['category'] == 'camera')
        sensor_line = next(line for line in result['line_items'] if line['category'] == 'sensor')

        self.assertEqual(pos_line['source_type'], 'paapi')
        self.assertEqual(pos_line['quantity'], 5)
        self.assertEqual(camera_line['source_type'], 'excel')
        self.assertEqual(camera_line['quantity'], 4)
        self.assertEqual(sensor_line['source_type'], 'excel')
        self.assertEqual(sensor_line['quantity'], 5)

    def test_tablet_endpoint_does_not_misclassify_gateway_as_tablet(self):
        self.items.append(
            FakeItem(
                id=uuid.uuid4(),
                type=CatalogItemType.DEVICE,
                name='T-Mobile 5G Gateway G5AR-1',
                sku='PAPI-GATEWAY-5G',
                vendor='PAPI',
                vendor_sku='G5AR-1',
                description='5G internet gateway',
                price=0.0,
                attributes={
                    'category': 'laptop',
                    'product_type': 'laptop',
                    'source_type': 'paapi',
                    'source_name': 'papi_catalog',
                },
            )
        )

        result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 2, 'recommendedSwitches': 1},
                'counts': {'switchCount': 1, 'indoorAPsFinal': 2},
                'inputsNormalized': {'switchPorts': 24, 'pricing': {'taxPct': 0}},
            },
            business_context={'tablets': 2},
            preferences={},
        )

        tablet_line = next(line for line in result['line_items'] if line['category'] == 'tablet')
        self.assertIn('placeholder', tablet_line['name'].lower())

    def test_bom_adds_typed_cabling_line_with_meter_pricing(self):
        result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 3, 'recommendedSwitches': 2},
                'counts': {'switchCount': 2, 'indoorAPsFinal': 3},
                'inputsNormalized': {'totalFloorAreaSqft': 2500, 'pricing': {'taxPct': 0}},
            },
            preferences={'cableType': 'CAT6e'},
        )

        cable_line = next(line for line in result['line_items'] if line['category'] == 'cabling')
        self.assertEqual(cable_line['sku'], 'CAT6e')
        self.assertEqual(cable_line['cable_type'], 'CAT6e')
        self.assertEqual(cable_line['unit_price'], 0.8)
        self.assertGreater(cable_line['quantity'], 0)
        self.assertGreater(cable_line['cable_length_meters'], 0)
        self.assertEqual(cable_line['connectivity'], 'wired')

    def test_endpoint_connectivity_rules_keep_wireless_and_sim_out_of_cable_drops(self):
        result = NetworkBomService(self.service).generate_bom_from_estimate(
            calculator_result={
                'summary': {'recommendedIndoorAPs': 2, 'recommendedSwitches': 1},
                'counts': {'switchCount': 1, 'indoorAPsFinal': 2},
                'inputsNormalized': {'totalFloorAreaSqft': 2000, 'pricing': {'taxPct': 0}},
            },
            business_context={
                'laptops': 5,
                'mobilePhones': 7,
                'needsBackupInternet': 'Yes',
            },
            preferences={},
        )

        laptop_line = next(line for line in result['line_items'] if line['category'] == 'laptop')
        phone_line = next(line for line in result['line_items'] if line['category'] == 'phone')
        backup_line = next(line for line in result['line_items'] if line['category'] == 'cellular_backup')
        cable_line = next(line for line in result['line_items'] if line['category'] == 'cabling')

        self.assertEqual(laptop_line['connectivity'], 'wireless')
        self.assertEqual(phone_line['connectivity'], 'wireless')
        self.assertEqual(backup_line['connectivity'], 'sim')
        self.assertEqual(cable_line['wired_drop_count'], 3)  # 2 AP uplinks + 1 switch uplink


if __name__ == '__main__':
    unittest.main()
