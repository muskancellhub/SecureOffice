from __future__ import annotations

import unittest

from app.models.network_design import NetworkDesignStatus
from app.models.order import OrderStatus
from app.models.quote import BillingType, QuoteLineType, QuoteStatus
from app.services.network_design_service import NetworkDesignService


class _FakeUserRepo:
    def get_by_id(self, _user_id: str):
        return object()


class _FakeRepo:
    def get_design_by_id(self, _design_id: str):
        return None


class _FakeOnboardingRepo:
    class _Profile:
        organization_name = None
        admin_name = None
        admin_email = None
        admin_phone = None
        metadata_json = {}
        company_setup_completed = False
        duns_number = None
        tax_id = None
        credit_validation_status = 'PENDING'
        tax_validation_status = 'PENDING'
        onboarding_completed = False

    def __init__(self):
        self.profile = self._Profile()

    def get_or_create(self, _tenant_id):
        return self.profile


class _FakeDB:
    def get(self, _model, _pk):
        return None


class TestDesignQuoteMapping(unittest.TestCase):
    def setUp(self):
        self.service = NetworkDesignService(
            _FakeDB(),
            repo=_FakeRepo(),
            onboarding_repo=_FakeOnboardingRepo(),
            user_repo=_FakeUserRepo(),
        )

    def test_category_to_quote_line_type(self):
        self.assertEqual(self.service._line_type_for_category('wifi_ap'), QuoteLineType.DEVICE)
        self.assertEqual(self.service._line_type_for_category('managed_service_candidate'), QuoteLineType.SERVICE)

    def test_category_to_billing_defaults(self):
        billing, interval = self.service._billing_defaults_for_category('managed_service')
        self.assertEqual(billing, BillingType.RECURRING)
        self.assertEqual(interval.value, 'MONTH')

        one_time_billing, one_time_interval = self.service._billing_defaults_for_category('switch')
        self.assertEqual(one_time_billing, BillingType.ONE_TIME)
        self.assertIsNone(one_time_interval)

    def test_design_status_to_quote_status_mapping(self):
        self.assertEqual(
            self.service._quote_status_for_design_status(NetworkDesignStatus.DRAFT),
            QuoteStatus.DRAFT,
        )
        self.assertEqual(
            self.service._quote_status_for_design_status(NetworkDesignStatus.SUBMITTED),
            QuoteStatus.SENT,
        )
        self.assertEqual(
            self.service._quote_status_for_design_status(NetworkDesignStatus.APPROVED),
            QuoteStatus.ACCEPTED,
        )
        self.assertEqual(
            self.service._quote_status_for_design_status(NetworkDesignStatus.COMPLETED),
            QuoteStatus.CONVERTED,
        )

    def test_design_status_to_order_status_mapping(self):
        self.assertEqual(
            self.service._order_status_for_design_status(NetworkDesignStatus.REVIEWED),
            OrderStatus.SUBMITTED,
        )
        self.assertEqual(
            self.service._order_status_for_design_status(NetworkDesignStatus.PROPOSAL_READY),
            OrderStatus.PROCESSING,
        )
        self.assertEqual(
            self.service._order_status_for_design_status(NetworkDesignStatus.FULFILLMENT_IN_PROGRESS),
            OrderStatus.VENDOR_ORDERED,
        )
        self.assertEqual(
            self.service._order_status_for_design_status(NetworkDesignStatus.COMPLETED),
            OrderStatus.ACTIVE,
        )

    def test_decomposition_buckets(self):
        buckets = self.service._build_decomposition_from_bom(
            {
                'line_items': [
                    {'name': 'Indoor AP', 'category': 'wifi_ap', 'quantity': 3, 'unit_price': 199, 'line_total': 597},
                    {'name': 'Firewall', 'category': 'firewall', 'quantity': 1, 'unit_price': 899, 'line_total': 899},
                    {'name': 'Install labor', 'category': 'installation', 'quantity': 1, 'unit_price': 500, 'line_total': 500},
                ]
            }
        )
        self.assertEqual(len(buckets['networkHardware']), 1)
        self.assertEqual(len(buckets['connectivity']), 1)
        self.assertEqual(len(buckets['installation']), 1)


if __name__ == '__main__':
    unittest.main()
