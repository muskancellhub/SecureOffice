import importlib.util
import unittest

from app.services.network_vendor_catalog_loader import (
    NETWORK_VENDOR_CATALOG_SOURCE_NAME,
    load_network_vendor_catalog,
    normalize_network_vendor_row,
)


class TestNetworkVendorCatalogLoader(unittest.TestCase):
    @unittest.skipIf(importlib.util.find_spec('openpyxl') is None, 'openpyxl not installed in current environment')
    def test_load_network_vendor_catalog_rows(self):
        result = load_network_vendor_catalog()

        self.assertGreater(len(result.rows), 0)
        self.assertGreaterEqual(len(result.rows), 80)

        vendors = {row['vendor'] for row in result.rows}
        self.assertTrue({'Meraki', 'Extreme Networks', 'SkyMirr', 'InHand'}.issubset(vendors))

        first = result.rows[0]
        self.assertEqual(first['attributes']['source_type'], 'excel')
        self.assertEqual(first['attributes']['source_name'], NETWORK_VENDOR_CATALOG_SOURCE_NAME)

        quote_only_rows = [row for row in result.rows if row['price'] is None]
        self.assertGreaterEqual(len(quote_only_rows), 1)

    def test_normalize_network_vendor_row_mapping(self):
        normalized = normalize_network_vendor_row(
            {
                'Vendor': 'Meraki',
                'Category': 'Wireless AP',
                'Model': 'MR36',
                'Family/Type': 'Indoor Wi-Fi 6 AP',
                'Price': '368.32',
                'Currency': 'USD',
                'Pricing basis': 'Public street price',
                'Official catalog source': 'https://example.com/catalog',
                'Public price source': 'https://example.com/price',
                'Notes': 'sample',
            },
            row_number=2,
        )

        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized['attributes']['category'], 'wifi_ap')
        self.assertEqual(normalized['attributes']['product_type'], 'wifi_ap')
        self.assertEqual(normalized['vendor'], 'Meraki')
        self.assertAlmostEqual(float(normalized['price']), 368.32)


if __name__ == '__main__':
    unittest.main()
