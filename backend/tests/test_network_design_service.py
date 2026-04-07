from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import unittest
import uuid

from app.core.exceptions import AppError
from app.models.network_design import NetworkDesignStatus
from app.services.network_design_service import NetworkDesignService


@dataclass
class FakeLead:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    user_id: uuid.UUID | None
    full_name: str
    email: str
    company_name: str
    phone: str | None
    notes: str | None
    metadata_json: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FakeDesign:
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    design_name: str | None
    status: NetworkDesignStatus
    calculator_input_json: dict = field(default_factory=dict)
    calculator_result_json: dict = field(default_factory=dict)
    bom_json: dict = field(default_factory=dict)
    topology_json: dict = field(default_factory=dict)
    drawio_xml: str | None = None
    assumptions_json: list = field(default_factory=list)
    estimate_capex: float | None = None
    ap_count: int = 0
    switch_count: int = 0
    session_key: str | None = None
    submitted_at: datetime | None = None
    status_updated_at: datetime | None = None
    status_history_json: list = field(default_factory=list)
    milestones_json: dict = field(default_factory=dict)
    updates_json: list = field(default_factory=list)
    install_assistance_json: dict = field(default_factory=dict)
    decomposition_json: dict = field(default_factory=dict)
    metadata_json: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    lead: FakeLead | None = None


class FakeRepo:
    def __init__(self):
        self.leads: list[FakeLead] = []
        self.designs: list[FakeDesign] = []

    def create_lead(self, **kwargs):
        lead = FakeLead(id=uuid.uuid4(), **kwargs)
        self.leads.append(lead)
        return lead

    def find_lead(self, *, email: str, company_name: str, tenant_id=None):
        email_l = email.lower().strip()
        company_l = company_name.lower().strip()
        normalized_tenant = uuid.UUID(str(tenant_id)) if tenant_id is not None else None
        for lead in self.leads:
            if (
                lead.email.lower() == email_l
                and lead.company_name.lower() == company_l
                and lead.tenant_id == normalized_tenant
            ):
                return lead
        return None

    def create_design(self, **kwargs):
        design = FakeDesign(id=uuid.uuid4(), **kwargs)
        self.designs.append(design)
        self._link_lead(design)
        return design

    def get_design_by_id(self, design_id: str):
        try:
            target = uuid.UUID(str(design_id))
        except Exception:
            return None
        for design in self.designs:
            if design.id == target:
                self._link_lead(design)
                return design
        return None

    def list_for_user(self, *, user_id: str, submitted_only: bool = False):
        user_uuid = uuid.UUID(user_id)
        rows = [row for row in self.designs if row.created_by_user_id == user_uuid]
        if submitted_only:
            rows = [row for row in rows if row.status != NetworkDesignStatus.DRAFT]
        for row in rows:
            self._link_lead(row)
        return sorted(rows, key=lambda row: row.updated_at, reverse=True)

    def list_for_tenant(self, *, tenant_id: str, submitted_only: bool = False):
        tenant_uuid = uuid.UUID(tenant_id)
        rows = [row for row in self.designs if row.tenant_id == tenant_uuid]
        if submitted_only:
            rows = [row for row in rows if row.status != NetworkDesignStatus.DRAFT]
        for row in rows:
            self._link_lead(row)
        return sorted(rows, key=lambda row: row.updated_at, reverse=True)

    def list_ops_submissions(self, *, tenant_id: str):
        tenant_uuid = uuid.UUID(tenant_id)
        included = {
            NetworkDesignStatus.SUBMITTED,
            NetworkDesignStatus.IN_REVIEW,
            NetworkDesignStatus.BOM_FINALIZED,
            NetworkDesignStatus.PROPOSAL_READY,
            NetworkDesignStatus.APPROVED,
            NetworkDesignStatus.ORDER_DECOMPOSED,
            NetworkDesignStatus.FULFILLMENT_IN_PROGRESS,
            NetworkDesignStatus.INSTALLATION_SCHEDULED,
            NetworkDesignStatus.INSTALLED,
            NetworkDesignStatus.COMPLETED,
        }
        rows = [row for row in self.designs if row.tenant_id == tenant_uuid and row.status in included]
        for row in rows:
            self._link_lead(row)
        return sorted(rows, key=lambda row: row.updated_at, reverse=True)

    def _link_lead(self, design: FakeDesign):
        design.lead = next((lead for lead in self.leads if lead.id == design.lead_id), None)


class FakeOnboarding:
    def __init__(self):
        self.profile = type(
            'Profile',
            (),
            {
                'organization_name': None,
                'admin_name': None,
                'admin_email': None,
                'admin_phone': None,
                'metadata_json': {},
            },
        )()

    def get_or_create(self, _tenant_id):
        return self.profile


class FakeUserRepo:
    def __init__(self, valid_user_ids: list[str]):
        self.valid_user_ids = set(valid_user_ids)

    def get_by_id(self, user_id: str):
        return object() if user_id in self.valid_user_ids else None


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def delete(self, _obj):
        return None

    def flush(self):
        return None

    def get(self, _model, _id):
        return None

    def scalar(self, _stmt):
        return None

    class _ScalarResult:
        @staticmethod
        def all():
            return []

    def scalars(self, _stmt):
        return self._ScalarResult()

    def commit(self):
        return None


class DemoAwareNetworkDesignService(NetworkDesignService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.synced = []

    def _sync_existing_tables_for_design(self, *, design, current_user):
        self.synced.append(str(design.id))
        design.metadata_json = {
            **(design.metadata_json or {}),
            'source': 'generated_from_calculator',
            'quoteId': design.metadata_json.get('quoteId') or f'quote-{str(design.id)[:8]}',
            'orderId': design.metadata_json.get('orderId') or f'order-{str(design.id)[:8]}',
            'workflowInstanceId': design.metadata_json.get('workflowInstanceId') or f'wf-{str(design.id)[:8]}',
            'assetId': design.metadata_json.get('assetId') or f'asset-{str(design.id)[:8]}',
        }


class TestNetworkDesignService(unittest.TestCase):
    def setUp(self):
        self.repo = FakeRepo()
        self.onboarding_repo = FakeOnboarding()
        self.user_id = str(uuid.uuid4())
        self.admin_id = str(uuid.uuid4())
        self.tenant_id = str(uuid.uuid4())
        self.notifier_calls: list[dict] = []
        self.service = DemoAwareNetworkDesignService(
            FakeDB(),
            repo=self.repo,
            onboarding_repo=self.onboarding_repo,
            user_repo=FakeUserRepo([self.user_id, self.admin_id]),
            mail_notifier=lambda payload: self.notifier_calls.append(payload),
        )
        self.actor = {'user_id': self.user_id, 'tenant_id': self.tenant_id, 'role': 'USER'}
        self.admin = {'user_id': self.admin_id, 'tenant_id': self.tenant_id, 'role': 'ADMIN'}

    def _submit_design(self) -> FakeDesign:
        return self.service.save_design(
            self.actor,
            {
                'submit': True,
                'calculator_result': {'summary': {'estimatedCapEx': 12500, 'recommendedIndoorAPs': 4, 'recommendedSwitches': 1}},
                'bom': {'line_items': []},
                'lead': {'fullName': 'Alice Buyer', 'email': 'alice@example.com', 'companyName': 'Blue Diner'},
            },
        )

    def test_lead_creation_and_design_link_on_submission(self):
        design = self._submit_design()

        self.assertEqual(len(self.repo.leads), 1)
        self.assertIsNotNone(design.lead_id)
        self.assertEqual(design.lead.company_name, 'Blue Diner')
        self.assertEqual(design.status, NetworkDesignStatus.SUBMITTED)

    def test_same_lead_reused_for_multiple_designs(self):
        first = self._submit_design()
        second = self.service.save_design(
            self.actor,
            {
                'submit': False,
                'lead': {'fullName': 'Alice Buyer', 'email': 'alice@example.com', 'companyName': 'Blue Diner'},
                'calculator_result': {'summary': {'estimatedCapEx': 7000}},
            },
        )
        self.assertEqual(len(self.repo.leads), 1)
        self.assertEqual(first.lead_id, second.lead_id)

    def test_status_history_tracking(self):
        design = self._submit_design()
        self.assertGreaterEqual(len(design.status_history_json), 1)

        in_review = self.service.update_status(self.admin, str(design.id), 'in_review', note='Initial technical review started.')
        self.assertEqual(in_review.status, NetworkDesignStatus.IN_REVIEW)
        self.assertEqual(in_review.status_history_json[-1]['status'], 'in_review')
        self.assertEqual(in_review.status_history_json[-1]['note'], 'Initial technical review started.')

    def test_current_status_updates_through_demo_flow(self):
        design = self._submit_design()
        for status in ['in_review', 'bom_finalized', 'proposal_ready', 'approved', 'order_decomposed']:
            design = self.service.update_status(self.admin, str(design.id), status)
        self.assertEqual(design.status, NetworkDesignStatus.ORDER_DECOMPOSED)

    def test_milestone_persistence(self):
        design = self._submit_design()
        updated = self.service.update_milestones(
            self.admin,
            str(design.id),
            {
                'estimatedProposalDate': '2026-04-12',
                'estimatedInstallationDate': '2026-04-26',
                'confirmedInstallationDate': '2026-04-28',
            },
        )
        self.assertEqual(updated.milestones_json.get('estimatedProposalDate'), '2026-04-12')
        self.assertEqual(updated.milestones_json.get('confirmedInstallationDate'), '2026-04-28')

    def test_customer_visible_vs_internal_notes(self):
        design = self._submit_design()
        with_internal = self.service.add_update_note(
            self.admin,
            str(design.id),
            {'visibility': 'internal', 'message': 'Waiting on final AP stock check.'},
        )
        with_customer = self.service.add_update_note(
            self.admin,
            str(design.id),
            {'visibility': 'customer', 'message': 'Proposal draft prepared for review.'},
        )

        internal_visible = self.service.filter_updates(with_customer.updates_json, include_internal=True)
        customer_visible = self.service.filter_updates(with_internal.updates_json, include_internal=False)
        self.assertEqual(len(internal_visible), 2)
        self.assertEqual(len(customer_visible), 1)
        self.assertEqual(customer_visible[0]['message'], 'Proposal draft prepared for review.')

    def test_internal_ops_view_listing_submitted_requests(self):
        self.service.save_design(self.actor, {'submit': False, 'status': 'draft'})
        submitted = self._submit_design()
        self.service.update_status(self.admin, str(submitted.id), 'in_review')

        ops_rows = self.service.list_designs(self.admin, ops_view=True)
        self.assertEqual(len(ops_rows), 1)
        self.assertEqual(ops_rows[0].status, NetworkDesignStatus.IN_REVIEW)

    def test_reopen_existing_design_payload(self):
        design = self.service.save_design(
            self.actor,
            {
                'submit': False,
                'designName': 'HQ Network',
                'calculatorInput': {'totalFloorAreaSqft': 12000},
                'calculatorResult': {'summary': {'estimatedCapEx': 9300}},
                'bom': {'line_items': [{'category': 'wifi_ap', 'quantity': 3}]},
                'topology': {'nodes': [{'id': 'node-internet'}], 'edges': []},
                'drawioXml': '<xml/>',
                'lead': {'fullName': 'Alice Buyer', 'email': 'alice@example.com', 'companyName': 'Blue Diner'},
            },
        )

        reopened = self.service.get_design(self.actor, str(design.id))
        self.assertEqual(reopened.design_name, 'HQ Network')
        self.assertEqual((reopened.bom_json.get('line_items') or [])[0]['category'], 'wifi_ap')
        self.assertEqual(reopened.topology_json.get('nodes')[0]['id'], 'node-internet')

    def test_decomposition_bucket_mapping_from_bom(self):
        design = self.service.save_design(
            self.actor,
            {
                'submit': False,
                'bom': {
                    'line_items': [
                        {'name': 'AP', 'category': 'wifi_ap', 'quantity': 4, 'unit_price': 100, 'line_total': 400},
                        {'name': 'Firewall', 'category': 'firewall', 'quantity': 1, 'unit_price': 800, 'line_total': 800},
                        {'name': 'Managed', 'category': 'managed_service_candidate', 'quantity': 1, 'unit_price': 120, 'line_total': 120},
                        {'name': 'Cabling', 'category': 'installation', 'quantity': 1, 'unit_price': 500, 'line_total': 500},
                        {'name': 'Bracket', 'category': 'accessory', 'quantity': 2, 'unit_price': 25, 'line_total': 50},
                    ]
                },
            },
        )
        decomposition = design.decomposition_json
        self.assertEqual(len(decomposition.get('networkHardware') or []), 1)
        self.assertEqual(len(decomposition.get('connectivity') or []), 1)
        self.assertEqual(len(decomposition.get('managedServices') or []), 1)
        self.assertEqual(len(decomposition.get('installation') or []), 1)
        self.assertEqual(len(decomposition.get('accessories') or []), 1)

    def test_install_mode_persistence(self):
        design = self._submit_design()
        updated = self.service.update_install_assistance(
            self.actor,
            str(design.id),
            {
                'installMode': 'remote_assistance',
                'preferredInstallDate': '2026-05-01',
                'installNotes': 'Need after-hours slot.',
            },
        )
        self.assertEqual(updated.install_assistance_json.get('installMode'), 'remote_assistance')
        self.assertEqual(updated.install_assistance_json.get('preferredInstallDate'), '2026-05-01')

    def test_required_lead_validation_for_submission(self):
        with self.assertRaises(AppError):
            self.service.save_design(
                self.actor,
                {
                    'submit': True,
                    'lead': {'fullName': '', 'email': '', 'companyName': ''},
                },
            )

    def test_generated_design_records_quote_order_workflow_metadata(self):
        design = self._submit_design()
        metadata = design.metadata_json or {}
        self.assertEqual(metadata.get('source'), 'generated_from_calculator')
        self.assertTrue(str(metadata.get('quoteId') or '').startswith('quote-'))
        self.assertTrue(str(metadata.get('orderId') or '').startswith('order-'))
        self.assertTrue(str(metadata.get('workflowInstanceId') or '').startswith('wf-'))
        self.assertIn(str(design.id), self.service.synced)

    def test_status_update_keeps_workflow_linkage_metadata(self):
        design = self._submit_design()
        updated = self.service.update_status(self.admin, str(design.id), 'in_review')
        metadata = updated.metadata_json or {}
        self.assertIn('workflowInstanceId', metadata)
        self.assertGreaterEqual(self.service.synced.count(str(design.id)), 2)


if __name__ == '__main__':
    unittest.main()
