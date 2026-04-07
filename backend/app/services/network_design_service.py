from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models.catalog import BillingCycle, CatalogItem, CatalogItemType
from app.models.lifecycle import Asset, AssetStatus, WorkflowInstance, WorkflowStatus, WorkflowStep, WorkflowStepStatus
from app.models.network_design import NetworkDesign, NetworkDesignStatus
from app.models.onboarding import TenantOnboarding
from app.models.order import Order, OrderLine, OrderStatus
from app.models.quote import BillingInterval, BillingType, Quote, QuoteLine, QuoteLineType, QuoteStatus
from app.models.tenant import Tenant
from app.models.user import UserRole
from app.repositories.network_design_repository import NetworkDesignRepository
from app.repositories.onboarding_repository import OnboardingRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.quote_repository import QuoteRepository
from app.repositories.user_repository import UserRepository
from app.services.email_service import EmailService


class NetworkDesignService:
    DEMO_WORKFLOW_TEMPLATE = 'demo_design_lifecycle'
    DEMO_WORKFLOW_STAGES: list[tuple[str, str]] = [
        ('draft', 'Draft'),
        ('reviewed', 'Reviewed'),
        ('submitted', 'Submitted'),
        ('in_review', 'In Review'),
        ('bom_finalized', 'BOM Finalized'),
        ('proposal_ready', 'Proposal Ready'),
        ('approved', 'Approved'),
        ('order_decomposed', 'Order Decomposed'),
        ('fulfillment_in_progress', 'Fulfillment In Progress'),
        ('installation_scheduled', 'Installation Scheduled'),
        ('installed', 'Installed'),
        ('completed', 'Completed'),
    ]

    STATUS_SEQUENCE: list[NetworkDesignStatus] = [
        NetworkDesignStatus.DRAFT,
        NetworkDesignStatus.REVIEWED,
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
    ]

    ALLOWED_ADMIN_TRANSITIONS: dict[NetworkDesignStatus, set[NetworkDesignStatus]] = {
        NetworkDesignStatus.DRAFT: {NetworkDesignStatus.REVIEWED, NetworkDesignStatus.SUBMITTED},
        NetworkDesignStatus.REVIEWED: {NetworkDesignStatus.SUBMITTED},
        NetworkDesignStatus.SUBMITTED: {NetworkDesignStatus.IN_REVIEW},
        NetworkDesignStatus.IN_REVIEW: {NetworkDesignStatus.BOM_FINALIZED},
        NetworkDesignStatus.BOM_FINALIZED: {NetworkDesignStatus.PROPOSAL_READY},
        NetworkDesignStatus.PROPOSAL_READY: {NetworkDesignStatus.APPROVED},
        NetworkDesignStatus.APPROVED: {NetworkDesignStatus.ORDER_DECOMPOSED},
        NetworkDesignStatus.ORDER_DECOMPOSED: {NetworkDesignStatus.FULFILLMENT_IN_PROGRESS},
        NetworkDesignStatus.FULFILLMENT_IN_PROGRESS: {
            NetworkDesignStatus.INSTALLATION_SCHEDULED,
            NetworkDesignStatus.INSTALLED,
        },
        NetworkDesignStatus.INSTALLATION_SCHEDULED: {NetworkDesignStatus.INSTALLED},
        NetworkDesignStatus.INSTALLED: {NetworkDesignStatus.COMPLETED},
        NetworkDesignStatus.COMPLETED: set(),
    }

    MILESTONE_KEYS: tuple[str, ...] = (
        'estimatedReviewDate',
        'estimatedProposalDate',
        'estimatedFulfillmentDate',
        'estimatedInstallationDate',
        'confirmedFulfillmentDate',
        'confirmedInstallationDate',
    )

    def __init__(
        self,
        db,
        *,
        repo: NetworkDesignRepository | None = None,
        onboarding_repo: OnboardingRepository | None = None,
        quote_repo: QuoteRepository | None = None,
        order_repo: OrderRepository | None = None,
        user_repo: UserRepository | None = None,
        mail_notifier: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.db = db
        self.repo = repo or NetworkDesignRepository(db)
        self.onboarding_repo = onboarding_repo or OnboardingRepository(db)
        self.quote_repo = quote_repo or QuoteRepository(db)
        self.order_repo = order_repo or OrderRepository(db)
        self.user_repo = user_repo or UserRepository(db)
        self.mail_notifier = mail_notifier or self._default_mail_notifier

    @staticmethod
    def _default_mail_notifier(payload: dict[str, Any]) -> None:
        EmailService.send_design_submission_handoff(payload)

    @staticmethod
    def _is_admin(role: str | None) -> bool:
        return role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            raise AppError(f'Invalid {field_name}', 400)

    @staticmethod
    def _clean_text(value: Any) -> str | None:
        text = str(value or '').strip()
        return text or None

    @staticmethod
    def _as_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _status_rank(cls, status: NetworkDesignStatus) -> int:
        try:
            return cls.STATUS_SEQUENCE.index(status)
        except ValueError:
            return -1

    @staticmethod
    def _normalize_visibility(value: Any) -> str:
        if str(value or '').strip().lower() == 'customer':
            return 'customer'
        return 'internal'

    @staticmethod
    def _actor_label(current_user: dict | None) -> str | None:
        if not current_user:
            return None
        return current_user.get('email') or current_user.get('user_id') or current_user.get('role')

    def _assert_user_exists(self, current_user: dict | None) -> None:
        if not current_user:
            return
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found')

    def _normalize_lead_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        required: bool,
    ) -> dict[str, str | None] | None:
        if not payload:
            if required:
                raise AppError('Lead/contact info is required before submission', 422)
            return None

        full_name = self._clean_text(payload.get('full_name') or payload.get('fullName'))
        email = self._clean_text(payload.get('email'))
        company_name = self._clean_text(payload.get('company_name') or payload.get('companyName'))
        phone = self._clean_text(payload.get('phone'))
        notes = self._clean_text(payload.get('notes'))

        if required:
            if not full_name:
                raise AppError('Lead full name is required', 422)
            if not email:
                raise AppError('Lead email is required', 422)
            if not company_name:
                raise AppError('Lead company name is required', 422)

        if email and '@' not in email:
            raise AppError('Lead email must be valid', 422)

        return {
            'full_name': full_name,
            'email': email.lower() if email else None,
            'company_name': company_name,
            'phone': phone,
            'notes': notes,
        }

    def _normalize_milestones_payload(self, payload: dict[str, Any] | None) -> dict[str, str]:
        if not payload:
            return {}

        alias_map = {
            'estimated_review_date': 'estimatedReviewDate',
            'estimatedReviewDate': 'estimatedReviewDate',
            'estimated_proposal_date': 'estimatedProposalDate',
            'estimatedProposalDate': 'estimatedProposalDate',
            'estimated_fulfillment_date': 'estimatedFulfillmentDate',
            'estimatedFulfillmentDate': 'estimatedFulfillmentDate',
            'estimated_installation_date': 'estimatedInstallationDate',
            'estimatedInstallationDate': 'estimatedInstallationDate',
            'confirmed_fulfillment_date': 'confirmedFulfillmentDate',
            'confirmedFulfillmentDate': 'confirmedFulfillmentDate',
            'confirmed_installation_date': 'confirmedInstallationDate',
            'confirmedInstallationDate': 'confirmedInstallationDate',
        }

        normalized: dict[str, str] = {}
        for key, target in alias_map.items():
            value = self._clean_text(payload.get(key))
            if value is not None:
                normalized[target] = value
        return normalized

    def _normalize_install_assistance_payload(self, payload: dict[str, Any] | None) -> dict[str, str]:
        if not payload:
            return {}
        install_mode = self._clean_text(payload.get('install_mode') or payload.get('installMode'))
        preferred_install_date = self._clean_text(payload.get('preferred_install_date') or payload.get('preferredInstallDate'))
        install_notes = self._clean_text(payload.get('install_notes') or payload.get('installNotes'))

        normalized: dict[str, str] = {}
        if install_mode is not None:
            valid_modes = {'self_install', 'remote_assistance', 'onsite_visit'}
            if install_mode not in valid_modes:
                raise AppError(f"Invalid install mode. Allowed values: {', '.join(sorted(valid_modes))}", 422)
            normalized['installMode'] = install_mode
        if preferred_install_date is not None:
            normalized['preferredInstallDate'] = preferred_install_date
        if install_notes is not None:
            normalized['installNotes'] = install_notes
        return normalized

    @staticmethod
    def _merge_non_empty(existing: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing or {})
        for key, value in patch.items():
            if value is not None:
                merged[key] = value
        return merged

    def _derive_summary(self, payload: dict[str, Any]) -> tuple[float, int, int, list[str]]:
        calculator_result = payload.get('calculator_result') or payload.get('calculatorResult') or {}
        bom = payload.get('bom') or {}
        topology = payload.get('topology') or {}

        summary = calculator_result.get('summary') or {}
        costs = calculator_result.get('costs') or {}

        ap_count = self._as_int(summary.get('recommendedIndoorAPs'), 0)
        switch_count = self._as_int(summary.get('recommendedSwitches'), 0)
        estimate_capex = self._as_float(summary.get('estimatedCapEx'), 0.0)

        if ap_count <= 0 or switch_count <= 0:
            for line in (bom.get('line_items') or bom.get('lineItems') or []):
                category = str(line.get('category') or '').strip().lower()
                if category == 'wifi_ap':
                    ap_count += max(1, self._as_int(line.get('quantity'), 1))
                if category == 'switch':
                    switch_count += max(1, self._as_int(line.get('quantity'), 1))

        if estimate_capex <= 0:
            estimate_capex = self._as_float(costs.get('capExFinal'), self._as_float(bom.get('grand_total'), 0.0))

        assumptions = []
        assumptions.extend(str(v) for v in (bom.get('assumptions') or []))
        assumptions.extend(str(v) for v in ((topology.get('metadata') or {}).get('assumptions') or []))
        assumptions.extend(str(v) for v in (payload.get('assumptions') or []))
        deduped_assumptions = list(dict.fromkeys([v for v in assumptions if v]))
        return round(estimate_capex, 2), ap_count, switch_count, deduped_assumptions

    def _resolve_status_for_save(self, payload: dict[str, Any]) -> NetworkDesignStatus:
        submit = bool(payload.get('submit'))
        if submit:
            return NetworkDesignStatus.SUBMITTED

        raw_status = payload.get('status')
        if not raw_status:
            return NetworkDesignStatus.DRAFT
        try:
            status = NetworkDesignStatus(str(raw_status))
        except Exception:
            allowed = ', '.join(status.value for status in NetworkDesignStatus)
            raise AppError(f'Invalid status. Allowed values: {allowed}', 422)
        if status not in {NetworkDesignStatus.DRAFT, NetworkDesignStatus.REVIEWED}:
            raise AppError('Draft save only supports status draft or reviewed. Use submit/status endpoints for later stages.', 422)
        return status

    def _assert_design_access(self, current_user: dict, design: NetworkDesign) -> None:
        if self._is_admin(current_user.get('role')):
            if design.tenant_id and str(design.tenant_id) != current_user['tenant_id']:
                raise ForbiddenError('Design not found in your tenant')
            return
        if not design.created_by_user_id or str(design.created_by_user_id) != current_user['user_id']:
            raise ForbiddenError('Design not found for current user')

    def _upsert_lead(
        self,
        *,
        current_user: dict | None,
        lead_payload: dict[str, str | None] | None,
    ):
        if not lead_payload:
            return None
        email = lead_payload.get('email')
        company_name = lead_payload.get('company_name')
        if not email or not company_name:
            return None

        tenant_id = current_user['tenant_id'] if current_user else None
        user_id = current_user['user_id'] if current_user else None

        existing = self.repo.find_lead(email=email, company_name=company_name, tenant_id=tenant_id)
        if existing:
            if lead_payload.get('full_name'):
                existing.full_name = str(lead_payload['full_name'])
            if lead_payload.get('phone') is not None:
                existing.phone = lead_payload.get('phone')
            if lead_payload.get('notes') is not None:
                existing.notes = lead_payload.get('notes')
            if user_id and not existing.user_id:
                existing.user_id = self._parse_uuid(user_id, field_name='user_id')
            return existing

        lead = self.repo.create_lead(
            tenant_id=self._parse_uuid(tenant_id, field_name='tenant_id') if tenant_id else None,
            user_id=self._parse_uuid(user_id, field_name='user_id') if user_id else None,
            full_name=str(lead_payload['full_name'] or ''),
            email=str(email).lower().strip(),
            company_name=str(company_name).strip(),
            phone=lead_payload.get('phone'),
            notes=lead_payload.get('notes'),
            metadata_json={},
        )
        return lead

    def _sync_onboarding_contact(self, current_user: dict | None, lead_payload: dict[str, str | None] | None) -> None:
        if not current_user or not lead_payload:
            return
        tenant_uuid = self._parse_uuid(current_user['tenant_id'], field_name='tenant_id')
        profile = self.onboarding_repo.get_or_create(tenant_uuid)
        tenant = self.db.get(Tenant, tenant_uuid)
        if tenant and lead_payload.get('company_name'):
            tenant.name = str(lead_payload.get('company_name'))
        profile.organization_name = lead_payload.get('company_name') or profile.organization_name
        profile.admin_name = lead_payload.get('full_name') or profile.admin_name
        profile.admin_email = lead_payload.get('email') or profile.admin_email
        profile.admin_phone = lead_payload.get('phone') or profile.admin_phone
        profile.company_setup_completed = True
        if not profile.duns_number and not profile.tax_id:
            profile.duns_number = 'DEMO'
        profile.credit_validation_status = 'VERIFIED'
        profile.tax_validation_status = 'VERIFIED'
        profile.onboarding_completed = True
        profile.metadata_json = {
            **(profile.metadata_json or {}),
            'demo_lead_capture_notes': lead_payload.get('notes'),
        }

    def _ensure_status_history(self, design: NetworkDesign) -> None:
        history = list(design.status_history_json or [])
        if history:
            return
        seed_time = (design.submitted_at or design.status_updated_at or design.updated_at or design.created_at or self._now()).isoformat()
        history.append(
            {
                'status': design.status.value if hasattr(design.status, 'value') else str(design.status),
                'changedAt': seed_time,
                'changedBy': None,
                'note': None,
            }
        )
        design.status_history_json = history
        if not design.status_updated_at:
            design.status_updated_at = self._now()

    def _append_status_event(
        self,
        design: NetworkDesign,
        *,
        status: NetworkDesignStatus,
        current_user: dict | None,
        note: str | None = None,
    ) -> bool:
        now = self._now()
        self._ensure_status_history(design)
        history = list(design.status_history_json or [])

        last_status = history[-1].get('status') if history else None
        if last_status == status.value and design.status == status:
            if note:
                history[-1]['note'] = note
            design.status_history_json = history
            return False

        history.append(
            {
                'status': status.value,
                'changedAt': now.isoformat(),
                'changedBy': self._actor_label(current_user),
                'note': note,
            }
        )
        design.status_history_json = history
        design.status = status
        design.status_updated_at = now
        if status == NetworkDesignStatus.SUBMITTED and design.submitted_at is None:
            design.submitted_at = now
        return True

    @staticmethod
    def filter_updates(updates: list[dict[str, Any]], *, include_internal: bool) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for row in list(updates or []):
            if not isinstance(row, dict):
                continue
            visibility = str(row.get('visibility') or 'internal').lower()
            if visibility == 'internal' and not include_internal:
                continue
            filtered.append(row)
        return filtered

    @classmethod
    def next_milestone_label(cls, milestones: dict[str, Any]) -> str | None:
        if not milestones:
            return None
        label_map = {
            'estimatedReviewDate': 'Estimated review',
            'estimatedProposalDate': 'Estimated proposal',
            'estimatedFulfillmentDate': 'Estimated fulfillment',
            'estimatedInstallationDate': 'Estimated installation',
            'confirmedFulfillmentDate': 'Confirmed fulfillment',
            'confirmedInstallationDate': 'Confirmed installation',
        }
        for key in cls.MILESTONE_KEYS:
            value = str((milestones or {}).get(key) or '').strip()
            if value:
                return f"{label_map[key]}: {value}"
        return None

    def _append_update(
        self,
        design: NetworkDesign,
        *,
        visibility: str,
        message: str,
        current_user: dict | None,
    ) -> None:
        updates = list(design.updates_json or [])
        updates.append(
            {
                'id': str(uuid.uuid4()),
                'requestId': str(design.id),
                'createdAt': self._now().isoformat(),
                'author': self._actor_label(current_user),
                'visibility': self._normalize_visibility(visibility),
                'message': message,
            }
        )
        design.updates_json = updates

    def _build_decomposition_from_bom(self, bom: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        buckets: dict[str, list[dict[str, Any]]] = {
            'networkHardware': [],
            'connectivity': [],
            'managedServices': [],
            'installation': [],
            'accessories': [],
        }
        lines = (bom or {}).get('line_items') or (bom or {}).get('lineItems') or []
        for line in lines:
            if not isinstance(line, dict):
                continue
            category = str(line.get('category') or '').strip().lower()
            record = {
                'name': line.get('name'),
                'category': category or None,
                'quantity': self._as_int(line.get('quantity'), 0),
                'unitPrice': self._as_float(line.get('unit_price') or line.get('unitPrice'), 0.0),
                'lineTotal': self._as_float(line.get('line_total') or line.get('lineTotal'), 0.0),
                'vendor': line.get('vendor'),
                'sourceType': line.get('source_type') or line.get('sourceType'),
            }
            if category in {'router', 'firewall', 'security_appliance', 'cellular_gateway'}:
                buckets['connectivity'].append(record)
            elif category in {'managed_service', 'managed_service_candidate', 'service', 'license'}:
                buckets['managedServices'].append(record)
            elif category in {'installation', 'labor', 'cabling', 'deployment'}:
                buckets['installation'].append(record)
            elif category in {'accessory', 'antenna'}:
                buckets['accessories'].append(record)
            elif category in {'wifi_ap', 'switch', 'camera', 'sensor'}:
                buckets['networkHardware'].append(record)
            else:
                buckets['networkHardware'].append(record)
        return buckets

    def _refresh_decomposition(self, design: NetworkDesign) -> None:
        design.decomposition_json = self._build_decomposition_from_bom(design.bom_json or {})

    def _seed_default_milestones_if_missing(self, design: NetworkDesign) -> None:
        milestones = dict(design.milestones_json or {})
        if any(str(milestones.get(key) or '').strip() for key in self.MILESTONE_KEYS):
            return
        today = self._now().date()
        milestones.update(
            {
                'estimatedReviewDate': (today + timedelta(days=2)).isoformat(),
                'estimatedProposalDate': (today + timedelta(days=5)).isoformat(),
                'estimatedFulfillmentDate': (today + timedelta(days=12)).isoformat(),
                'estimatedInstallationDate': (today + timedelta(days=16)).isoformat(),
            }
        )
        design.milestones_json = milestones

    @staticmethod
    def _line_type_for_category(category: str | None) -> QuoteLineType:
        service_categories = {'managed_service', 'managed_service_candidate', 'service', 'license', 'installation', 'labor'}
        if str(category or '').strip().lower() in service_categories:
            return QuoteLineType.SERVICE
        return QuoteLineType.DEVICE

    @staticmethod
    def _billing_defaults_for_category(category: str | None) -> tuple[BillingType, BillingInterval | None]:
        recurring_categories = {'managed_service', 'managed_service_candidate', 'service', 'license'}
        if str(category or '').strip().lower() in recurring_categories:
            return BillingType.RECURRING, BillingInterval.MONTH
        return BillingType.ONE_TIME, None

    @staticmethod
    def _billing_from_catalog_item(item: CatalogItem | None) -> tuple[BillingType, BillingInterval | None]:
        if not item:
            return BillingType.ONE_TIME, None
        if item.billing_cycle == BillingCycle.MONTHLY:
            return BillingType.RECURRING, BillingInterval.MONTH
        if item.billing_cycle == BillingCycle.YEARLY:
            return BillingType.RECURRING, BillingInterval.YEAR
        return BillingType.ONE_TIME, None

    @classmethod
    def _quote_status_for_design_status(cls, status: NetworkDesignStatus) -> QuoteStatus:
        if status in {NetworkDesignStatus.DRAFT, NetworkDesignStatus.REVIEWED}:
            return QuoteStatus.DRAFT
        if status in {
            NetworkDesignStatus.SUBMITTED,
            NetworkDesignStatus.IN_REVIEW,
            NetworkDesignStatus.BOM_FINALIZED,
            NetworkDesignStatus.PROPOSAL_READY,
        }:
            return QuoteStatus.SENT
        if status == NetworkDesignStatus.COMPLETED:
            return QuoteStatus.CONVERTED
        return QuoteStatus.ACCEPTED

    @classmethod
    def _order_status_for_design_status(cls, status: NetworkDesignStatus) -> OrderStatus:
        if status in {NetworkDesignStatus.DRAFT, NetworkDesignStatus.REVIEWED, NetworkDesignStatus.SUBMITTED}:
            return OrderStatus.SUBMITTED
        if status in {
            NetworkDesignStatus.IN_REVIEW,
            NetworkDesignStatus.BOM_FINALIZED,
            NetworkDesignStatus.PROPOSAL_READY,
            NetworkDesignStatus.APPROVED,
            NetworkDesignStatus.ORDER_DECOMPOSED,
        }:
            return OrderStatus.PROCESSING
        if status == NetworkDesignStatus.FULFILLMENT_IN_PROGRESS:
            return OrderStatus.VENDOR_ORDERED
        if status in {NetworkDesignStatus.INSTALLATION_SCHEDULED, NetworkDesignStatus.INSTALLED}:
            return OrderStatus.SHIPPED
        return OrderStatus.ACTIVE

    def _find_catalog_item_from_bom_line(self, line: dict[str, Any]) -> CatalogItem | None:
        item_id = self._clean_text(line.get('item_id') or line.get('itemId'))
        if item_id:
            try:
                item = self.db.get(CatalogItem, self._parse_uuid(item_id, field_name='item_id'))
                if item:
                    return item
            except AppError:
                pass

        sku = self._clean_text(line.get('sku'))
        if sku:
            stmt = select(CatalogItem).where(CatalogItem.sku == sku)
            return self.db.scalar(stmt)
        return None

    def _replace_quote_lines_from_bom(self, quote: Quote, bom: dict[str, Any]) -> None:
        for existing in list(quote.lines or []):
            self.db.delete(existing)
        self.db.flush()

        one_time_total = 0.0
        recurring_total = 0.0
        lines = (bom or {}).get('line_items') or (bom or {}).get('lineItems') or []
        for line in lines:
            if not isinstance(line, dict):
                continue
            category = self._clean_text(line.get('category')) or ''
            name = self._clean_text(line.get('name')) or 'Generated line item'
            quantity = max(1, self._as_int(line.get('quantity'), 1))
            unit_price = round(self._as_float(line.get('unit_price') or line.get('unitPrice'), 0.0), 2)
            list_price = round(self._as_float(line.get('list_price') or line.get('listPrice'), unit_price), 2)
            source_type = self._clean_text(line.get('source_type') or line.get('sourceType')) or 'generated'
            selection_reason = self._clean_text(line.get('selection_reason') or line.get('selectionReason'))

            catalog_item = self._find_catalog_item_from_bom_line(line)
            line_type = self._line_type_for_category(category)
            billing_type, interval = self._billing_defaults_for_category(category)
            if catalog_item:
                line_type = QuoteLineType.SERVICE if catalog_item.type == CatalogItemType.SERVICE else QuoteLineType.DEVICE
                billing_type, interval = self._billing_from_catalog_item(catalog_item)

            quote_line = QuoteLine(
                quote_id=quote.id,
                line_type=line_type,
                catalog_item_id=catalog_item.id if catalog_item else None,
                name_snapshot=name,
                sku_snapshot=self._clean_text(line.get('sku')),
                vendor_snapshot=self._clean_text(line.get('vendor')) or (catalog_item.vendor if catalog_item else None),
                qty=quantity,
                list_price_snapshot=list_price,
                final_unit_price_snapshot=unit_price,
                billing_type=billing_type,
                interval=interval,
                metadata_json={
                    'category': category,
                    'source_type': source_type,
                    'selection_reason': selection_reason,
                    'line_id': self._clean_text(line.get('line_id') or line.get('lineId')),
                },
                parent_line_id=None,
            )
            self.db.add(quote_line)

            line_total = round(unit_price * quantity, 2)
            if billing_type == BillingType.RECURRING:
                recurring_total += line_total
            else:
                one_time_total += line_total

        quote.one_time_total = round(one_time_total, 2)
        quote.monthly_total = round(recurring_total, 2)
        quote.projected_12_month_cost = round(one_time_total + (recurring_total * 12), 2)
        self.db.flush()

    def _upsert_quote_for_design(self, *, design: NetworkDesign, current_user: dict, status: NetworkDesignStatus) -> Quote:
        metadata = dict(design.metadata_json or {})
        quote_id = metadata.get('quoteId') or metadata.get('quote_id')
        quote = self.quote_repo.get_by_id(str(quote_id)) if quote_id else None

        if not quote:
            quote = self.quote_repo.create(
                tenant_id=self._parse_uuid(current_user['tenant_id'], field_name='tenant_id'),
                created_by_user_id=self._parse_uuid(current_user['user_id'], field_name='user_id'),
                status=self._quote_status_for_design_status(status),
                one_time_total=0.0,
                monthly_total=0.0,
                projected_12_month_cost=0.0,
                currency='USD',
            )
            self.db.flush()

        quote.status = self._quote_status_for_design_status(status)
        quote.currency = 'USD'
        self._replace_quote_lines_from_bom(quote, design.bom_json or {})
        self.db.flush()
        return quote

    def _upsert_order_for_quote(self, *, quote: Quote, current_user: dict, status: NetworkDesignStatus) -> Order:
        order = self.db.scalar(
            select(Order)
            .where(Order.quote_id == quote.id)
            .options(selectinload(Order.lines))
        )
        if not order:
            order = Order(
                tenant_id=quote.tenant_id,
                created_by_user_id=self._parse_uuid(current_user['user_id'], field_name='user_id'),
                quote_id=quote.id,
                status=self._order_status_for_design_status(status),
            )
            self.db.add(order)
            self.db.flush()

        order.status = self._order_status_for_design_status(status)

        for existing in list(order.lines or []):
            self.db.delete(existing)
        self.db.flush()

        for quote_line in list(quote.lines or []):
            order_line = OrderLine(
                order_id=order.id,
                line_type=quote_line.line_type,
                catalog_item_id=quote_line.catalog_item_id,
                name_snapshot=quote_line.name_snapshot,
                sku_snapshot=quote_line.sku_snapshot,
                vendor_snapshot=quote_line.vendor_snapshot,
                qty=quote_line.qty,
                list_price_snapshot=float(quote_line.list_price_snapshot),
                final_unit_price_snapshot=float(quote_line.final_unit_price_snapshot),
                billing_type=quote_line.billing_type,
                interval=quote_line.interval,
                metadata_json=quote_line.metadata_json or {},
                parent_line_id=None,
            )
            self.db.add(order_line)
        self.db.flush()
        return order

    def _sync_demo_workflow(
        self,
        *,
        order: Order,
        status: NetworkDesignStatus,
    ) -> WorkflowInstance:
        workflow = self.db.scalar(
            select(WorkflowInstance)
            .where(WorkflowInstance.order_id == order.id)
            .options(selectinload(WorkflowInstance.steps))
        )
        if not workflow:
            workflow = WorkflowInstance(
                tenant_id=order.tenant_id,
                order_id=order.id,
                template_key=self.DEMO_WORKFLOW_TEMPLATE,
                status=WorkflowStatus.ACTIVE,
                current_stage=status.value,
            )
            self.db.add(workflow)
            self.db.flush()

        existing_steps = {step.stage_key: step for step in (workflow.steps or [])}
        for sequence, (stage_key, display_name) in enumerate(self.DEMO_WORKFLOW_STAGES):
            if stage_key in existing_steps:
                step = existing_steps[stage_key]
                step.sequence = sequence
                step.display_name = display_name
            else:
                step = WorkflowStep(
                    workflow_instance_id=workflow.id,
                    stage_key=stage_key,
                    display_name=display_name,
                    sequence=sequence,
                    status=WorkflowStepStatus.PENDING,
                    retries=0,
                    started_at=None,
                    completed_at=None,
                    metadata_json={},
                )
                self.db.add(step)
                self.db.flush()

        now = self._now()
        current_index = next(
            (idx for idx, (stage_key, _) in enumerate(self.DEMO_WORKFLOW_STAGES) if stage_key == status.value),
            0,
        )
        steps = list(
            self.db.scalars(
                select(WorkflowStep)
                .where(WorkflowStep.workflow_instance_id == workflow.id)
                .order_by(WorkflowStep.sequence.asc())
            ).all()
        )
        for idx, step in enumerate(steps):
            if status == NetworkDesignStatus.COMPLETED:
                step.status = WorkflowStepStatus.DONE
                step.started_at = step.started_at or now
                step.completed_at = now
                continue

            if idx < current_index:
                step.status = WorkflowStepStatus.DONE
                step.started_at = step.started_at or now
                step.completed_at = step.completed_at or now
            elif idx == current_index:
                step.status = WorkflowStepStatus.IN_PROGRESS
                step.started_at = step.started_at or now
                step.completed_at = None
            else:
                step.status = WorkflowStepStatus.PENDING
                step.completed_at = None
                step.started_at = None

        workflow.current_stage = status.value
        workflow.status = WorkflowStatus.COMPLETED if status == NetworkDesignStatus.COMPLETED else WorkflowStatus.ACTIVE
        self.db.flush()
        return workflow

    def _upsert_design_asset(
        self,
        *,
        design: NetworkDesign,
        current_user: dict,
        quote: Quote,
        order: Order,
        workflow: WorkflowInstance,
    ) -> Asset:
        tenant_id = self._parse_uuid(current_user['tenant_id'], field_name='tenant_id')
        owner_user_id = self._parse_uuid(current_user['user_id'], field_name='user_id')
        asset = None
        existing_assets = list(
            self.db.scalars(
                select(Asset)
                .where(
                    Asset.tenant_id == tenant_id,
                    Asset.asset_type == 'design_artifact',
                )
                .order_by(Asset.created_at.desc())
            ).all()
        )
        for candidate in existing_assets:
            if str((candidate.metadata_json or {}).get('design_id')) == str(design.id):
                asset = candidate
                break

        if not asset:
            asset = Asset(
                tenant_id=tenant_id,
                contract_id=None,
                order_line_id=None,
                name=design.design_name or f'Generated Design {str(design.id)[:8]}',
                sku=f'DESIGN-{str(design.id)[:8]}',
                vendor='SecureOffice2',
                asset_type='design_artifact',
                status=AssetStatus.ACTIVE,
                owner_user_id=owner_user_id,
                location=None,
                serial_number=None,
                metadata_json={},
            )
            self.db.add(asset)

        asset.name = design.design_name or asset.name
        asset.metadata_json = {
            **(asset.metadata_json or {}),
            'design_id': str(design.id),
            'quote_id': str(quote.id),
            'order_id': str(order.id),
            'workflow_instance_id': str(workflow.id),
            'status': design.status.value if hasattr(design.status, 'value') else str(design.status),
            'bom_snapshot': design.bom_json or {},
            'topology_snapshot': design.topology_json or {},
            'drawio_xml': design.drawio_xml,
            'assumptions': list(design.assumptions_json or []),
        }
        self.db.flush()
        return asset

    def _sync_existing_tables_for_design(
        self,
        *,
        design: NetworkDesign,
        current_user: dict | None,
    ) -> None:
        if not current_user:
            return
        quote = self._upsert_quote_for_design(design=design, current_user=current_user, status=design.status)
        order = self._upsert_order_for_quote(quote=quote, current_user=current_user, status=design.status)
        workflow = self._sync_demo_workflow(order=order, status=design.status)
        asset = self._upsert_design_asset(
            design=design,
            current_user=current_user,
            quote=quote,
            order=order,
            workflow=workflow,
        )
        design.metadata_json = {
            **(design.metadata_json or {}),
            'source': 'generated_from_calculator',
            'quoteId': str(quote.id),
            'orderId': str(order.id),
            'workflowInstanceId': str(workflow.id),
            'assetId': str(asset.id),
        }

    def save_design(self, current_user: dict | None, payload: dict[str, Any]) -> NetworkDesign:
        self._assert_user_exists(current_user)

        status = self._resolve_status_for_save(payload)
        lead_payload = self._normalize_lead_payload(payload.get('lead'), required=(status == NetworkDesignStatus.SUBMITTED))
        lead = self._upsert_lead(current_user=current_user, lead_payload=lead_payload)
        self._sync_onboarding_contact(current_user, lead_payload)
        estimate_capex, ap_count, switch_count, assumptions = self._derive_summary(payload)
        milestones_patch = self._normalize_milestones_payload(payload.get('milestones'))
        install_patch = self._normalize_install_assistance_payload(
            payload.get('install_assistance') or payload.get('installAssistance')
        )

        design_name = self._clean_text(payload.get('design_name') or payload.get('designName'))
        if not design_name and lead_payload and lead_payload.get('company_name'):
            design_name = f"{lead_payload.get('company_name')} SMB Network Design"

        design_id = payload.get('design_id') or payload.get('designId')
        if design_id:
            design = self.repo.get_design_by_id(str(design_id))
            if not design:
                raise NotFoundError('Design not found')
            if current_user:
                self._assert_design_access(current_user, design)
        else:
            design = self.repo.create_design(
                tenant_id=self._parse_uuid(current_user['tenant_id'], field_name='tenant_id') if current_user else None,
                created_by_user_id=self._parse_uuid(current_user['user_id'], field_name='user_id') if current_user else None,
                lead_id=lead.id if lead else None,
                design_name=design_name,
                status=status,
                calculator_input_json={},
                calculator_result_json={},
                bom_json={},
                topology_json={},
                drawio_xml=None,
                assumptions_json=[],
                estimate_capex=0,
                ap_count=0,
                switch_count=0,
                session_key=self._clean_text(payload.get('session_key') or payload.get('sessionKey')),
                status_updated_at=self._now(),
                status_history_json=[],
                milestones_json={},
                updates_json=[],
                install_assistance_json={},
                decomposition_json={},
                metadata_json={},
            )

        previous_status = design.status
        had_submitted_timestamp = design.submitted_at is not None

        if lead:
            design.lead_id = lead.id
        if design_name is not None:
            design.design_name = design_name

        design.calculator_input_json = payload.get('calculator_input') or payload.get('calculatorInput') or {}
        design.calculator_result_json = payload.get('calculator_result') or payload.get('calculatorResult') or {}
        design.bom_json = payload.get('bom') or {}
        design.topology_json = payload.get('topology') or {}
        design.drawio_xml = payload.get('drawio_xml') or payload.get('drawioXml')
        design.assumptions_json = assumptions
        design.estimate_capex = estimate_capex
        design.ap_count = ap_count
        design.switch_count = switch_count
        design.session_key = self._clean_text(payload.get('session_key') or payload.get('sessionKey')) or design.session_key
        design.metadata_json = payload.get('metadata') or payload.get('rawSource') or design.metadata_json or {}

        if milestones_patch:
            design.milestones_json = self._merge_non_empty(design.milestones_json, milestones_patch)
        if install_patch:
            design.install_assistance_json = self._merge_non_empty(design.install_assistance_json, install_patch)

        status_changed = self._append_status_event(design, status=status, current_user=current_user)
        self._refresh_decomposition(design)

        if self._status_rank(design.status) >= self._status_rank(NetworkDesignStatus.SUBMITTED):
            self._seed_default_milestones_if_missing(design)
        self._sync_existing_tables_for_design(design=design, current_user=current_user)

        if design.status == NetworkDesignStatus.SUBMITTED:
            became_submitted = (not had_submitted_timestamp) or (previous_status != NetworkDesignStatus.SUBMITTED) or status_changed
            if became_submitted:
                self.mail_notifier(self.serialize_submission_payload(design))

        self.db.commit()
        refreshed = self.repo.get_design_by_id(str(design.id))
        if not refreshed:
            raise NotFoundError('Design not found after save')
        return refreshed

    def submit_design(self, current_user: dict, design_id: str, payload: dict[str, Any]) -> NetworkDesign:
        self._assert_user_exists(current_user)
        design = self.repo.get_design_by_id(design_id)
        if not design:
            raise NotFoundError('Design not found')
        self._assert_design_access(current_user, design)

        had_submitted_timestamp = design.submitted_at is not None

        lead_payload = self._normalize_lead_payload(payload.get('lead'), required=True)
        lead = self._upsert_lead(current_user=current_user, lead_payload=lead_payload)
        self._sync_onboarding_contact(current_user, lead_payload)
        if lead:
            design.lead_id = lead.id

        self._append_status_event(design, status=NetworkDesignStatus.SUBMITTED, current_user=current_user)
        self._seed_default_milestones_if_missing(design)

        if lead_payload and lead_payload.get('notes'):
            design.metadata_json = {
                **(design.metadata_json or {}),
                'submission_notes': lead_payload.get('notes'),
            }
            self._append_update(
                design,
                visibility='customer',
                message=str(lead_payload.get('notes')),
                current_user=current_user,
            )

        self._refresh_decomposition(design)
        self._sync_existing_tables_for_design(design=design, current_user=current_user)

        if not had_submitted_timestamp:
            self.mail_notifier(self.serialize_submission_payload(design))

        self.db.commit()
        refreshed = self.repo.get_design_by_id(str(design.id))
        if not refreshed:
            raise NotFoundError('Design not found after submit')
        return refreshed

    def list_designs(self, current_user: dict, *, submitted_only: bool = False, ops_view: bool = False) -> list[NetworkDesign]:
        self._assert_user_exists(current_user)
        if ops_view:
            if not self._is_admin(current_user.get('role')):
                raise ForbiddenError('Ops view is available to ADMIN or SUPER_ADMIN only')
            return self.repo.list_ops_submissions(tenant_id=current_user['tenant_id'])

        if self._is_admin(current_user.get('role')):
            return self.repo.list_for_tenant(tenant_id=current_user['tenant_id'], submitted_only=submitted_only)
        return self.repo.list_for_user(user_id=current_user['user_id'], submitted_only=submitted_only)

    def get_design(self, current_user: dict, design_id: str) -> NetworkDesign:
        self._assert_user_exists(current_user)
        design = self.repo.get_design_by_id(design_id)
        if not design:
            raise NotFoundError('Design not found')
        self._assert_design_access(current_user, design)
        return design

    def _fetch_design_for_tenant_admin(self, current_user: dict, design_id: str) -> NetworkDesign:
        design = self.repo.get_design_by_id(design_id)
        if not design:
            raise NotFoundError('Design not found')
        if design.tenant_id and str(design.tenant_id) != current_user['tenant_id']:
            raise ForbiddenError('Design not found in your tenant')
        return design

    def update_status(
        self,
        current_user: dict,
        design_id: str,
        status: str,
        *,
        note: str | None = None,
        note_visibility: str = 'internal',
    ) -> NetworkDesign:
        self._assert_user_exists(current_user)
        if not self._is_admin(current_user.get('role')):
            raise ForbiddenError('Only ADMIN or SUPER_ADMIN can update design status')

        design = self._fetch_design_for_tenant_admin(current_user, design_id)

        try:
            target = NetworkDesignStatus(status)
        except Exception:
            allowed = ', '.join(row.value for row in NetworkDesignStatus)
            raise AppError(f'Invalid status. Allowed values: {allowed}', 422)

        current_status = design.status
        if current_status != target:
            allowed_targets = self.ALLOWED_ADMIN_TRANSITIONS.get(current_status, set())
            if target not in allowed_targets:
                allowed = ', '.join(row.value for row in sorted(allowed_targets, key=lambda v: v.value)) or '(none)'
                raise AppError(
                    f'Invalid status transition from {current_status.value} to {target.value}. Allowed next statuses: {allowed}',
                    422,
                )

            self._append_status_event(design, status=target, current_user=current_user, note=note)
            if target == NetworkDesignStatus.SUBMITTED:
                self._seed_default_milestones_if_missing(design)
        elif note:
            self._append_status_event(design, status=target, current_user=current_user, note=note)

        if note:
            self._append_update(
                design,
                visibility=self._normalize_visibility(note_visibility),
                message=note,
                current_user=current_user,
            )

        self._refresh_decomposition(design)
        self._sync_existing_tables_for_design(design=design, current_user=current_user)
        self.db.commit()
        refreshed = self.repo.get_design_by_id(str(design.id))
        if not refreshed:
            raise NotFoundError('Design not found after status update')
        return refreshed

    def update_milestones(self, current_user: dict, design_id: str, milestones_payload: dict[str, Any]) -> NetworkDesign:
        self._assert_user_exists(current_user)
        if not self._is_admin(current_user.get('role')):
            raise ForbiddenError('Only ADMIN or SUPER_ADMIN can update milestones')

        design = self._fetch_design_for_tenant_admin(current_user, design_id)
        patch = self._normalize_milestones_payload(milestones_payload)
        if not patch:
            raise AppError('At least one milestone field is required', 422)

        design.milestones_json = self._merge_non_empty(design.milestones_json, patch)
        self._append_update(
            design,
            visibility='customer',
            message='Milestone dates were updated.',
            current_user=current_user,
        )
        self._sync_existing_tables_for_design(design=design, current_user=current_user)
        self.db.commit()

        refreshed = self.repo.get_design_by_id(str(design.id))
        if not refreshed:
            raise NotFoundError('Design not found after milestone update')
        return refreshed

    def update_install_assistance(self, current_user: dict, design_id: str, install_payload: dict[str, Any]) -> NetworkDesign:
        self._assert_user_exists(current_user)
        design = self.repo.get_design_by_id(design_id)
        if not design:
            raise NotFoundError('Design not found')
        self._assert_design_access(current_user, design)

        patch = self._normalize_install_assistance_payload(install_payload)
        if not patch:
            raise AppError('At least one installation preference field is required', 422)

        design.install_assistance_json = self._merge_non_empty(design.install_assistance_json, patch)

        if patch.get('installMode'):
            message = f"Installation preference updated to {patch['installMode'].replace('_', ' ')}."
            self._append_update(design, visibility='customer', message=message, current_user=current_user)

        self._sync_existing_tables_for_design(design=design, current_user=current_user)
        self.db.commit()
        refreshed = self.repo.get_design_by_id(str(design.id))
        if not refreshed:
            raise NotFoundError('Design not found after install update')
        return refreshed

    def add_update_note(self, current_user: dict, design_id: str, payload: dict[str, Any]) -> NetworkDesign:
        self._assert_user_exists(current_user)
        if not self._is_admin(current_user.get('role')):
            raise ForbiddenError('Only ADMIN or SUPER_ADMIN can add updates')

        design = self._fetch_design_for_tenant_admin(current_user, design_id)
        message = self._clean_text(payload.get('message'))
        if not message:
            raise AppError('Update message is required', 422)
        visibility = self._normalize_visibility(payload.get('visibility'))
        self._append_update(design, visibility=visibility, message=message, current_user=current_user)

        self._sync_existing_tables_for_design(design=design, current_user=current_user)
        self.db.commit()
        refreshed = self.repo.get_design_by_id(str(design.id))
        if not refreshed:
            raise NotFoundError('Design not found after note update')
        return refreshed

    @staticmethod
    def serialize_submission_payload(design: NetworkDesign) -> dict[str, Any]:
        lead = design.lead
        metadata = design.metadata_json or {}
        return {
            'design_id': str(design.id),
            'quote_id': metadata.get('quoteId') or metadata.get('quote_id'),
            'order_id': metadata.get('orderId') or metadata.get('order_id'),
            'workflow_instance_id': metadata.get('workflowInstanceId') or metadata.get('workflow_instance_id'),
            'design_name': design.design_name or f'Design {str(design.id)[:8]}',
            'status': design.status.value if hasattr(design.status, 'value') else str(design.status),
            'submitted_at': design.submitted_at.isoformat() if design.submitted_at else None,
            'estimated_capex': float(design.estimate_capex or 0),
            'ap_count': int(design.ap_count or 0),
            'switch_count': int(design.switch_count or 0),
            'lead': {
                'full_name': lead.full_name if lead else None,
                'email': lead.email if lead else None,
                'company_name': lead.company_name if lead else None,
                'phone': lead.phone if lead else None,
                'notes': lead.notes if lead else None,
            },
        }
