from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models.catalog import BillingCycle, CatalogItem, CatalogItemType
from app.models.order import OrderStatus
from app.models.quote import BillingInterval, BillingType, QuoteLineType, QuoteStatus
from app.models.product import Bundle, ComponentType, Product, ProductComponent
from app.models.user import UserRole
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.quote_repository import QuoteRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_logger import audit
from app.services.lifecycle_service import LifecycleService
from app.services.onboarding_service import OnboardingService
from app.services.order_notification_service import OrderNotificationService
from app.services.managed_service_pricing_service import ManagedServicePricingService
from app.services.component_pricing_service import ComponentPricingService
from app.services.capacity_service import check_capacity, format_violations
from app.services.pricing_service import PricingService

logger = logging.getLogger(__name__)

# Component types that cannot stand alone — they must attach to a DEVICE line
# (spec §5 "requires-a-device"). Enforced server-side at assembly time.
REQUIRES_DEVICE_TYPES = {
    ComponentType.LINE_CHARGE.value,
    ComponentType.SIM.value,
    ComponentType.BACKUP_SIM.value,
}


class QuoteService:
    def __init__(self, db):
        self.db = db
        self.quote_repo = QuoteRepository(db)
        self.order_repo = OrderRepository(db)
        self.cart_repo = CartRepository(db)
        self.user_repo = UserRepository(db)
        self.pricing_service = PricingService(db)
        self.onboarding_service = OnboardingService(db)

    def _assert_user_exists(self, current_user: dict):
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found')

    @staticmethod
    def _is_admin(role: str | None) -> bool:
        return role in {UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value}

    @staticmethod
    def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except (TypeError, ValueError):
            raise AppError(f'Invalid {field_name}', 400)

    def _assert_quote_access(self, current_user: dict, quote) -> None:
        role = current_user.get('role')
        if self._is_admin(role):
            if str(quote.tenant_id) != current_user['tenant_id']:
                raise ForbiddenError('Quote not found in your tenant')
            return
        if str(quote.created_by_user_id) != current_user['user_id']:
            raise ForbiddenError('Quote not found for current user')

    @staticmethod
    def _billing_from_catalog_item(item: CatalogItem) -> tuple[BillingType, BillingInterval | None]:
        if item.billing_cycle == BillingCycle.MONTHLY:
            return BillingType.RECURRING, BillingInterval.MONTH
        if item.billing_cycle == BillingCycle.YEARLY:
            return BillingType.RECURRING, BillingInterval.YEAR
        return BillingType.ONE_TIME, None

    @staticmethod
    def _line_type_from_catalog_item(item: CatalogItem) -> QuoteLineType:
        if item.type == CatalogItemType.SERVICE:
            return QuoteLineType.SERVICE
        return QuoteLineType.DEVICE

    @staticmethod
    def _normalize_pricing_basis(raw_basis: str | None) -> str:
        value = (raw_basis or '').strip().upper()
        if value == 'PER_SITE':
            return 'PER_SITE'
        return 'PER_DEVICE'

    @staticmethod
    def _service_quantity(*, router_qty: int, requested_qty: int | None, pricing_basis: str, num_sites: int) -> int:
        if pricing_basis == 'PER_SITE':
            return max(1, int(requested_qty or num_sites or 1))

        multiplier = max(1, int(requested_qty or 1))
        return max(1, int(router_qty)) * multiplier

    def _catalog_item_by_id(self, item_id: str, *, field_name: str = 'catalog_item_id') -> CatalogItem:
        item_uuid = self._parse_uuid(item_id, field_name=field_name)
        item = self.db.get(CatalogItem, item_uuid)
        if not item or not item.is_active:
            raise NotFoundError('Catalog item not found')
        return item

    def _build_line_candidates_from_draft(self, draft_solution: dict) -> tuple[list[dict], str]:
        requirements = draft_solution.get('requirements') or {}
        routers = draft_solution.get('routers') or []
        if not routers:
            raise AppError('Draft solution must include at least one router', 400)

        num_sites = int(requirements.get('num_sites') or 1)
        currency = str(draft_solution.get('currency') or 'USD').upper()
        candidates: list[dict] = []

        for index, router_input in enumerate(routers):
            router_item = self._catalog_item_by_id(router_input.get('catalog_item_id', ''), field_name='router.catalog_item_id')
            if router_item.type != CatalogItemType.DEVICE:
                raise AppError('Router entries must reference DEVICE catalog items', 400)

            router_qty = max(1, int(router_input.get('qty') or 1))
            router_temp_id = f'router-{index}'
            router_attrs = router_item.attributes or {}
            router_metadata = {
                'category': router_attrs.get('category'),
                'router_specs': router_attrs.get('specs') or {},
                'router_brand': router_attrs.get('brand'),
                'router_model': router_attrs.get('model'),
                'requirements': requirements,
            }

            billing_type, interval = self._billing_from_catalog_item(router_item)
            candidates.append(
                {
                    'temp_id': router_temp_id,
                    'parent_temp_id': None,
                    'catalog_item': router_item,
                    'qty': router_qty,
                    'line_type': self._line_type_from_catalog_item(router_item),
                    'billing_type': billing_type,
                    'interval': interval,
                    'metadata_json': router_metadata,
                }
            )

            attached_services = router_input.get('attached_services') or []
            for service_index, service_input in enumerate(attached_services):
                service_item = self._catalog_item_by_id(
                    service_input.get('catalog_item_id', ''),
                    field_name=f'router[{index}].attached_services[{service_index}].catalog_item_id',
                )
                if service_item.type != CatalogItemType.SERVICE:
                    raise AppError('Attached services must reference SERVICE catalog items', 400)

                service_attrs = service_item.attributes or {}
                allowed_categories = service_attrs.get('applies_to_categories') or []
                if allowed_categories and 'router' not in allowed_categories:
                    raise AppError('Selected service cannot be attached to a router', 400)

                requested_basis = service_input.get('pricing_basis')
                configured_basis = service_attrs.get('pricing_basis')
                pricing_basis = self._normalize_pricing_basis(requested_basis or configured_basis)
                service_qty = self._service_quantity(
                    router_qty=router_qty,
                    requested_qty=service_input.get('qty'),
                    pricing_basis=pricing_basis,
                    num_sites=num_sites,
                )

                service_billing_type, service_interval = self._billing_from_catalog_item(service_item)
                service_metadata = {
                    'category': service_attrs.get('category'),
                    'service_kind': service_attrs.get('service_kind'),
                    'service_tier': service_attrs.get('tier'),
                    'pricing_basis': pricing_basis,
                    'router_catalog_item_id': str(router_item.id),
                }

                candidates.append(
                    {
                        'temp_id': f'{router_temp_id}-service-{service_index}',
                        'parent_temp_id': router_temp_id,
                        'catalog_item': service_item,
                        'qty': service_qty,
                        'line_type': self._line_type_from_catalog_item(service_item),
                        'billing_type': service_billing_type,
                        'interval': service_interval,
                        'metadata_json': service_metadata,
                    }
                )

        return candidates, currency

    def _build_line_candidates_from_cart(self, current_user: dict) -> tuple[list[dict], str]:
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])
        if not cart.lines:
            raise AppError('Cart is empty', 400)

        candidates: list[dict] = []
        for line in cart.lines:
            item = self.db.get(CatalogItem, line.catalog_item_id)
            if not item or not item.is_active:
                raise NotFoundError('Cart contains an inactive or missing catalog item')

            billing_type, interval = self._billing_from_catalog_item(item)
            snapshot = line.price_snapshot or {}
            metadata = {
                'category': snapshot.get('category'),
                'attributes': snapshot.get('attributes') or {},
                'source_cart_line_id': str(line.id),
            }

            candidates.append(
                {
                    'temp_id': str(line.id),
                    'parent_temp_id': str(line.applies_to_line_id) if line.applies_to_line_id else None,
                    'catalog_item': item,
                    'qty': line.quantity,
                    'line_type': self._line_type_from_catalog_item(item),
                    'billing_type': billing_type,
                    'interval': interval,
                    'metadata_json': metadata,
                }
            )

        currency = cart.lines[0].currency if cart.lines else 'USD'
        return candidates, currency

    def _price_candidates(
        self,
        current_user: dict,
        candidates: list[dict],
        *,
        incremental_discount_pct: Decimal = Decimal('0'),
    ) -> tuple[list[dict], Decimal, Decimal, Decimal, Decimal]:
        customer_pricing = self.pricing_service.get_or_create_customer_pricing(current_user['tenant_id'])
        default_pct = Decimal(str(customer_pricing.default_discount_pct))

        one_time_total = Decimal('0')
        monthly_total = Decimal('0')

        priced_candidates: list[dict] = []
        for candidate in candidates:
            item = candidate['catalog_item']
            list_price_row = self.pricing_service.resolve_list_price(tenant_id=current_user['tenant_id'], catalog_item=item)
            final_unit_price = self.pricing_service.calculate_final_unit_price(
                list_price=list_price_row.list_price,
                default_discount_pct=default_pct,
                incremental_discount_pct=incremental_discount_pct,
            )

            line_total = final_unit_price * Decimal(candidate['qty'])
            if candidate['billing_type'] == BillingType.RECURRING:
                monthly_total += line_total
            else:
                one_time_total += line_total

            priced_candidates.append(
                {
                    **candidate,
                    'catalog_item_id': item.id,
                    'name_snapshot': item.name,
                    'sku_snapshot': item.sku,
                    'vendor_snapshot': list_price_row.vendor or item.vendor or self.pricing_service.default_vendor_for_item(item),
                    'list_price_snapshot': float(list_price_row.list_price),
                    'final_unit_price_snapshot': float(final_unit_price),
                }
            )

        projected_12_month_cost = one_time_total + (monthly_total * Decimal('12'))
        return (
            priced_candidates,
            self.pricing_service._quantize_money(one_time_total),
            self.pricing_service._quantize_money(monthly_total),
            self.pricing_service._quantize_money(projected_12_month_cost),
            default_pct,
        )

    def preview_quote(self, current_user: dict, draft_solution: dict) -> dict:
        self._assert_user_exists(current_user)
        # Gate deliberately checks the actor's home tenant: the whole quote/cart/
        # pricing write path is home-tenant-bound, so the gate must match the
        # tenant being written. Effective-tenant (X-Tenant-Id) threading for
        # quotes is a separate phase — see docs/plans/multi-tenant-config.md.
        if not self.onboarding_service.is_onboarding_complete(current_user['tenant_id']):
            raise AppError('Complete onboarding before creating a procurement request', 400)
        candidates, currency = self._build_line_candidates_from_draft(draft_solution)
        _, one_time_total, monthly_total, projected_12_month_cost, default_pct = self._price_candidates(
            current_user,
            candidates,
            incremental_discount_pct=Decimal('0'),
        )
        self.db.commit()

        return {
            'one_time_total': float(one_time_total),
            'monthly_total': float(monthly_total),
            'projected_12_month_cost': float(projected_12_month_cost),
            'currency': currency,
            'default_discount_pct': float(default_pct),
            'incremental_discount_pct': 0.0,
        }

    def create_quote(self, current_user: dict, payload: dict | None = None):
        self._assert_user_exists(current_user)
        if not self.onboarding_service.is_onboarding_complete(current_user['tenant_id']):
            raise AppError('Complete onboarding before creating a procurement request', 400)

        if payload and payload.get('draft_solution'):
            candidates, currency = self._build_line_candidates_from_draft(payload['draft_solution'])
        else:
            candidates, currency = self._build_line_candidates_from_cart(current_user)

        (
            priced_candidates,
            one_time_total,
            monthly_total,
            projected_12_month_cost,
            _,
        ) = self._price_candidates(current_user, candidates, incremental_discount_pct=Decimal('0'))

        quote = self.quote_repo.create(
            tenant_id=self._parse_uuid(current_user['tenant_id'], field_name='tenant_id'),
            created_by_user_id=self._parse_uuid(current_user['user_id'], field_name='user_id'),
            status=QuoteStatus.DRAFT,
            one_time_total=one_time_total,
            monthly_total=monthly_total,
            projected_12_month_cost=projected_12_month_cost,
            currency=currency,
        )

        # Ensure a deal-pricing row exists for this quote.
        self.pricing_service.get_or_create_deal_pricing(quote)

        ordered_candidates = sorted(
            priced_candidates,
            key=lambda row: 1 if row['line_type'] == QuoteLineType.SERVICE else 0,
        )
        quote_line_id_by_temp_id: dict[str, str] = {}

        for candidate in ordered_candidates:
            parent_line_id = None
            parent_temp_id = candidate.get('parent_temp_id')
            if parent_temp_id:
                parent_line_id = quote_line_id_by_temp_id.get(parent_temp_id)

            created_line = self.quote_repo.add_line(
                quote_id=quote.id,
                line_type=candidate['line_type'],
                catalog_item_id=candidate['catalog_item_id'],
                name_snapshot=candidate['name_snapshot'],
                sku_snapshot=candidate['sku_snapshot'],
                vendor_snapshot=candidate['vendor_snapshot'],
                qty=int(candidate['qty']),
                list_price_snapshot=float(candidate['list_price_snapshot']),
                final_unit_price_snapshot=float(candidate['final_unit_price_snapshot']),
                billing_type=candidate['billing_type'],
                interval=candidate['interval'],
                metadata_json=candidate['metadata_json'] or {},
                parent_line_id=parent_line_id,
            )
            quote_line_id_by_temp_id[candidate['temp_id']] = str(created_line.id)

        # ── Inject managed-service per-SKU lines if design_id is provided ──
        design_id = (payload or {}).get('design_id')
        if design_id:
            try:
                from app.models.network_design import NetworkDesign
                design = self.db.get(NetworkDesign, design_id)
                if design:
                    ms_lines = ManagedServicePricingService(self.db).get_managed_service_lines_for_quote(design)
                    for ms_line in ms_lines:
                        self.quote_repo.add_line(
                            quote_id=quote.id,
                            line_type=QuoteLineType.SERVICE,
                            catalog_item_id=None,
                            name_snapshot=ms_line['name'],
                            sku_snapshot=ms_line['sku'],
                            vendor_snapshot=ms_line['vendor'],
                            qty=ms_line['qty'],
                            list_price_snapshot=ms_line['unit_price'],
                            final_unit_price_snapshot=ms_line['unit_price'],
                            billing_type=BillingType.RECURRING,
                            interval=BillingInterval.MONTH,
                            metadata_json=ms_line['metadata'],
                            parent_line_id=None,
                        )
                        monthly_total += Decimal(str(ms_line['unit_price'])) * Decimal(str(ms_line['qty']))

                    # Recalculate totals
                    projected_12_month_cost = one_time_total + (monthly_total * Decimal('12'))
                    quote.monthly_total = float(self.pricing_service._quantize_money(monthly_total))
                    quote.projected_12_month_cost = float(self.pricing_service._quantize_money(projected_12_month_cost))
            except Exception:
                logger.exception('Failed to add managed service lines from design %s', design_id)

        self.db.commit()
        audit.log(
            'quote_created',
            quote_id=str(quote.id),
            source='draft_solution' if (payload and payload.get('draft_solution')) else 'cart',
            design_id=design_id,
            line_count=len(ordered_candidates),
            one_time_total=float(one_time_total),
            monthly_total=float(quote.monthly_total),
        )
        return self.quote_repo.get_by_id(str(quote.id))

    # ── Component-driven quotes (Phase 3) ────────────────────────────────────
    @staticmethod
    def _billing_from_engine_line(line: dict) -> tuple[BillingType, BillingInterval | None]:
        billing = BillingType.RECURRING if line['billing'] == 'RECURRING' else BillingType.ONE_TIME
        interval = None
        if line.get('interval') == 'MONTH':
            interval = BillingInterval.MONTH
        elif line.get('interval') == 'YEAR':
            interval = BillingInterval.YEAR
        return billing, interval

    def _check_capacity(self, product, result: dict) -> None:
        """Block over-subscription of a device's capacity (§5, block + warn)."""
        from sqlalchemy import select
        comp_ids = [self._parse_uuid(l['component_id'], field_name='component_id') for l in result['lines']]
        if not comp_ids:
            return
        comps = {
            str(c.id): c
            for c in self.db.scalars(select(ProductComponent).where(ProductComponent.id.in_(comp_ids)))
        }
        provided = (product.attributes or {}).get('capacity') or {}
        consumers = [
            ((comps[l['component_id']].attributes or {}).get('consumes'), l['qty'])
            for l in result['lines'] if l['component_id'] in comps
        ]
        violations = check_capacity(provided, consumers)
        if violations:
            raise AppError(f'Device capacity exceeded — {format_violations(violations)}', 409)

    @staticmethod
    def _validate_requires_device(result: dict) -> None:
        """A LINE_CHARGE / SIM cannot stand alone — it needs a DEVICE line (§5)."""
        has_device = any(l['component_type'] == ComponentType.DEVICE.value for l in result['lines'])
        if has_device:
            return
        for line in result['lines']:
            if line['component_type'] in REQUIRES_DEVICE_TYPES:
                raise AppError(
                    f"{line['component_type']} requires a device line in the same quote", 400
                )

    def _component_line_kwargs(self, quote_id, product, financial_model, result, line, parent_line_id):
        billing_type, interval = self._billing_from_engine_line(line)
        line_type = QuoteLineType.DEVICE if line['component_type'] == ComponentType.DEVICE.value else QuoteLineType.SERVICE
        leasing = None
        term = None
        if line['financed']:
            leasing = product.leasing_pct if product.leasing_pct is not None else result['annual_rate_pct']
            term = result['term_months']
        return {
            'quote_id': quote_id,
            'line_type': line_type,
            'catalog_item_id': None,
            'name_snapshot': line['label'],
            'sku_snapshot': line['vendor_component_sku'],
            'vendor_snapshot': product.vendor,
            'qty': int(line['qty']),
            'list_price_snapshot': float(line['unit_price']),  # cost-plus: no separate list price
            'final_unit_price_snapshot': float(line['unit_price']),
            'billing_type': billing_type,
            'interval': interval,
            'metadata_json': {
                'margin_source': line['margin_source'],
                'financed': line['financed'],
                'source': 'component_engine',
            },
            'parent_line_id': parent_line_id,
            'component_type': line['component_type'],
            'financial_model': financial_model,
            'product_id': product.id,
            'component_id': self._parse_uuid(line['component_id'], field_name='component_id'),
            'cost_snapshot': line['vendor_cost'],
            'margin_pct_snapshot': line['margin_pct'],
            'leasing_pct_snapshot': leasing,
            'term_months': term,
        }

    def _write_component_lines(self, quote, product, result, financial_model) -> None:
        """Append one product's computed tree to a quote (device parent first)."""
        ordered = sorted(result['lines'], key=lambda l: 0 if l['component_type'] == ComponentType.DEVICE.value else 1)
        quote_line_id_by_component_id: dict[str, str] = {}
        for line in ordered:
            parent_line_id = None
            parent_cid = line.get('parent_component_id')
            if parent_cid:
                parent_line_id = quote_line_id_by_component_id.get(parent_cid)
            created = self.quote_repo.add_line(
                **self._component_line_kwargs(quote.id, product, financial_model, result, line, parent_line_id)
            )
            quote_line_id_by_component_id[line['component_id']] = str(created.id)

    def _persist_component_tree(self, quote, product, result, financial_model) -> None:
        """Replace the quote's component lines with one product's computed tree."""
        for line in list(quote.lines):
            if line.component_id is not None:
                self.db.delete(line)
        self.db.flush()
        self._write_component_lines(quote, product, result, financial_model)
        quote.one_time_total = result['one_time_total']
        quote.monthly_total = result['monthly_total']
        quote.projected_12_month_cost = self.pricing_service._quantize_money(
            result['one_time_total'] + result['monthly_total'] * Decimal('12')
        )
        quote.financial_model = result['financial_model']
        quote.subscription_interval = result['interval']

    def _resolve_financial_model(self, current_user: dict, financial_model: str) -> str:
        """Apply the (manual, Phase 3) OPEX-eligibility gate."""
        financial_model = (financial_model or 'CAPEX').upper()
        if financial_model == 'OPEX':
            customer_pricing = self.pricing_service.get_or_create_customer_pricing(current_user['tenant_id'])
            if not customer_pricing.opex_eligible:
                raise ForbiddenError('OPEX financing is not enabled for this customer')
        return financial_model

    def create_component_quote(self, current_user: dict, payload: dict):
        """Assemble a quote from a product + component selections (à-la-carte)."""
        self._assert_user_exists(current_user)
        if not self.onboarding_service.is_onboarding_complete(current_user['tenant_id']):
            raise AppError('Complete onboarding before creating a procurement request', 400)

        payload = payload or {}
        product_id = payload.get('product_id')
        if not product_id:
            raise AppError('product_id is required', 400)
        financial_model = self._resolve_financial_model(current_user, payload.get('financial_model'))
        interval = (payload.get('interval') or 'MONTH').upper()
        selections = {str(k): int(v) for k, v in (payload.get('selections') or {}).items()}

        product = self.db.get(Product, self._parse_uuid(str(product_id), field_name='product_id'))
        if product is None or not product.is_active:
            raise NotFoundError('Product not found')

        result = ComponentPricingService(self.db).price_product(
            product.id, financial_model=financial_model, interval=interval,
            selections=selections, tenant_id=current_user['tenant_id'],
        )
        self._validate_requires_device(result)
        self._check_capacity(product, result)

        quote = self.quote_repo.create(
            tenant_id=self._parse_uuid(current_user['tenant_id'], field_name='tenant_id'),
            created_by_user_id=self._parse_uuid(current_user['user_id'], field_name='user_id'),
            status=QuoteStatus.DRAFT,
            one_time_total=result['one_time_total'],
            monthly_total=result['monthly_total'],
            projected_12_month_cost=self.pricing_service._quantize_money(
                result['one_time_total'] + result['monthly_total'] * Decimal('12')
            ),
            currency='USD',
        )
        self.pricing_service.get_or_create_deal_pricing(quote)
        self._persist_component_tree(quote, product, result, financial_model)
        self.db.commit()
        audit.log(
            'quote_created',
            quote_id=str(quote.id),
            source='component',
            product_id=str(product.id),
            financial_model=financial_model,
            interval=interval,
            selection_count=len(selections),
        )
        return self.quote_repo.get_by_id(str(quote.id))

    def add_component_line(self, current_user: dict, quote_id: str, payload: dict):
        """Add / change quantity of a component on a draft component-quote ("2 → 3 lines").

        Re-prices the whole product from the updated selections so totals and the
        OPEX/annual treatment stay consistent. qty=0 removes the component.
        """
        quote = self.get_quote(current_user, quote_id)
        if quote.status != QuoteStatus.DRAFT:
            raise AppError('Can only modify a draft quote', 400)

        payload = payload or {}
        component_id = payload.get('component_id')
        if not component_id:
            raise AppError('component_id is required', 400)
        qty = int(payload.get('qty', 1))

        component = self.db.get(ProductComponent, self._parse_uuid(str(component_id), field_name='component_id'))
        if component is None or not component.is_active:
            raise NotFoundError('Component not found')
        product = self.db.get(Product, component.product_id)

        # Reconstruct current selections from the quote's existing component lines.
        selections: dict[str, int] = {}
        for line in quote.lines:
            if line.component_id is not None and str(line.product_id) == str(product.id):
                selections[str(line.component_id)] = line.qty
        if qty <= 0:
            selections.pop(str(component.id), None)
        else:
            selections[str(component.id)] = qty

        financial_model = self._resolve_financial_model(current_user, quote.financial_model or 'CAPEX')
        interval = quote.subscription_interval or 'MONTH'
        result = ComponentPricingService(self.db).price_product(
            product.id, financial_model=financial_model, interval=interval,
            selections=selections, tenant_id=current_user['tenant_id'],
        )
        self._validate_requires_device(result)
        self._check_capacity(product, result)
        self._persist_component_tree(quote, product, result, financial_model)
        self.db.commit()
        audit.log(
            'quote_updated',
            quote_id=str(quote.id),
            component_id=str(component.id),
            new_qty=qty,
            change='component_line',
        )
        return self.quote_repo.get_by_id(str(quote.id))

    def create_bundle_quote(self, current_user: dict, payload: dict):
        """Expand a bundle into a multi-product quote (Phase 5).

        Each non-optional bundle item is priced (required components) and its tree
        appended under the quote; per-product capacity is validated. Optional items
        are included when their product_id appears in payload['include'].
        Note: each bundle item is priced at qty 1 (multi-unit bundle items deferred).
        """
        self._assert_user_exists(current_user)
        if not self.onboarding_service.is_onboarding_complete(current_user['tenant_id']):
            raise AppError('Complete onboarding before creating a procurement request', 400)

        payload = payload or {}
        bundle_id = payload.get('bundle_id')
        if not bundle_id:
            raise AppError('bundle_id is required', 400)
        financial_model = self._resolve_financial_model(current_user, payload.get('financial_model'))
        interval = (payload.get('interval') or 'MONTH').upper()
        include = {str(x) for x in (payload.get('include') or [])}

        bundle = self.db.get(Bundle, self._parse_uuid(str(bundle_id), field_name='bundle_id'))
        if bundle is None or not bundle.is_active:
            raise NotFoundError('Bundle not found')
        items = sorted(bundle.items, key=lambda i: i.sort_order)
        if not items:
            raise AppError('Bundle has no items', 400)

        quote = self.quote_repo.create(
            tenant_id=self._parse_uuid(current_user['tenant_id'], field_name='tenant_id'),
            created_by_user_id=self._parse_uuid(current_user['user_id'], field_name='user_id'),
            status=QuoteStatus.DRAFT, one_time_total=Decimal('0'), monthly_total=Decimal('0'),
            projected_12_month_cost=Decimal('0'), currency='USD',
        )
        self.pricing_service.get_or_create_deal_pricing(quote)

        cps = ComponentPricingService(self.db)
        one_time_total = Decimal('0')
        monthly_total = Decimal('0')
        priced_any = False
        for item in items:
            if item.is_optional and str(item.product_id) not in include:
                continue
            product = self.db.get(Product, item.product_id)
            if product is None or not product.is_active:
                continue
            result = cps.price_product(
                product.id, financial_model=financial_model, interval=interval,
                selections={}, tenant_id=current_user['tenant_id'],
            )
            self._validate_requires_device(result)
            self._check_capacity(product, result)
            self._write_component_lines(quote, product, result, financial_model)
            one_time_total += result['one_time_total']
            monthly_total += result['monthly_total']
            priced_any = True

        if not priced_any:
            raise AppError('Bundle expanded to no active products', 400)

        quote.one_time_total = self.pricing_service._quantize_money(one_time_total)
        quote.monthly_total = self.pricing_service._quantize_money(monthly_total)
        quote.projected_12_month_cost = self.pricing_service._quantize_money(
            one_time_total + monthly_total * Decimal('12')
        )
        quote.financial_model = financial_model
        quote.subscription_interval = interval
        self.db.commit()
        audit.log(
            'quote_created',
            quote_id=str(quote.id),
            source='bundle',
            bundle_id=str(bundle.id),
            financial_model=financial_model,
            interval=interval,
        )
        return self.quote_repo.get_by_id(str(quote.id))

    def list_quotes(self, current_user: dict):
        self._assert_user_exists(current_user)
        if self._is_admin(current_user.get('role')):
            return self.quote_repo.list_for_tenant(current_user['tenant_id'])
        return self.quote_repo.list_for_user(current_user['user_id'])

    def get_quote(self, current_user: dict, quote_id: str):
        self._assert_user_exists(current_user)
        quote = self.quote_repo.get_by_id(quote_id)
        if not quote:
            raise NotFoundError('Quote not found')
        self._assert_quote_access(current_user, quote)
        return quote

    def send_quote(self, current_user: dict, quote_id: str):
        quote = self.get_quote(current_user, quote_id)
        if quote.status == QuoteStatus.CONVERTED:
            raise AppError('Quote cannot be sent in its current state', 400)
        old_status = quote.status
        quote.status = QuoteStatus.SENT
        self.db.commit()
        audit.log('quote_sent', quote_id=str(quote.id),
                  old_status=old_status.value, new_status=QuoteStatus.SENT.value)
        return self.quote_repo.get_by_id(str(quote.id))

    def accept_quote(self, current_user: dict, quote_id: str):
        quote = self.get_quote(current_user, quote_id)
        if quote.status == QuoteStatus.CONVERTED:
            raise AppError('Quote cannot be accepted in its current state', 400)
        old_status = quote.status
        quote.status = QuoteStatus.ACCEPTED
        self.db.commit()
        audit.log('quote_accepted', quote_id=str(quote.id),
                  old_status=old_status.value, new_status=QuoteStatus.ACCEPTED.value)
        return self.quote_repo.get_by_id(str(quote.id))

    def convert_quote(self, current_user: dict, quote_id: str):
        quote = self.get_quote(current_user, quote_id)
        if not self.onboarding_service.is_payment_validated(current_user['tenant_id']):
            raise AppError('Payment method validation is required before checkout conversion', 400)
        if quote.status == QuoteStatus.CONVERTED:
            raise AppError('Quote already converted', 400)
        if quote.status != QuoteStatus.ACCEPTED:
            raise AppError('Quote must be ACCEPTED before conversion', 400)
        if not quote.lines:
            raise AppError('Quote has no lines', 400)

        order = self.order_repo.create(
            tenant_id=quote.tenant_id,
            created_by_user_id=self._parse_uuid(current_user['user_id'], field_name='user_id'),
            quote_id=quote.id,
            status=OrderStatus.SUBMITTED,
        )
        # Carry the quote's financial model onto the order header.
        order.financial_model = quote.financial_model
        order.subscription_interval = quote.subscription_interval

        sorted_lines = sorted(
            quote.lines,
            key=lambda line: 1 if line.line_type == QuoteLineType.SERVICE else 0,
        )
        order_line_id_by_quote_line_id: dict[str, str] = {}

        for quote_line in sorted_lines:
            parent_line_id = None
            if quote_line.parent_line_id:
                parent_line_id = order_line_id_by_quote_line_id.get(str(quote_line.parent_line_id))

            order_line = self.order_repo.add_line(
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
                parent_line_id=parent_line_id,
                # Component-pricing snapshots (spec §4.8) — without these the
                # financial model is lost when a quote converts to an order.
                component_type=quote_line.component_type,
                financial_model=quote_line.financial_model,
                product_id=quote_line.product_id,
                component_id=quote_line.component_id,
                cost_snapshot=quote_line.cost_snapshot,
                margin_pct_snapshot=quote_line.margin_pct_snapshot,
                leasing_pct_snapshot=quote_line.leasing_pct_snapshot,
                term_months=quote_line.term_months,
            )
            order_line_id_by_quote_line_id[str(quote_line.id)] = str(order_line.id)

        LifecycleService(self.db).ensure_order_lifecycle(order, current_user)
        quote.status = QuoteStatus.CONVERTED
        self.db.commit()

        order_id = str(order.id)
        quote_id_text = str(quote.id)
        line_count = len(list(order.lines or []))
        audit.log('quote_converted', quote_id=quote_id_text, order_id=order_id, line_count=line_count)
        audit.log('order_placed', order_id=order_id, quote_id=quote_id_text,
                  line_count=line_count, financial_model=order.financial_model)
        logger.warning(
            '[ORDER NOTIFICATION TRIGGER] quote_id=%s order_id=%s tenant_id=%s user_id=%s line_count=%d',
            quote_id_text,
            order_id,
            str(order.tenant_id),
            current_user.get('user_id'),
            len(list(order.lines or [])),
        )

        try:
            sent = OrderNotificationService(self.db).send_order_captured_notification(order_id=order_id)
            logger.warning(
                '[ORDER NOTIFICATION RESULT] quote_id=%s order_id=%s sent=%s',
                quote_id_text,
                order_id,
                sent,
            )
        except Exception as exc:
            logger.exception('[ORDER NOTIFICATION ERROR] quote_id=%s order_id=%s error=%s', quote_id_text, order_id, exc)

        return self.quote_repo.get_by_id(quote_id_text), self.order_repo.get_by_id(order_id)
