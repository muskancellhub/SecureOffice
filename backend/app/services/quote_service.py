from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from app.core.exceptions import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.models.order import OrderStatus
from app.models.quote import BillingInterval, BillingType, QuoteLineType, QuoteStatus
from app.models.product import Bundle, ComponentType, Product, ProductComponent
from app.models.user import UserRole
from app.repositories.cart_repository import CartRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.quote_repository import QuoteRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_logger import audit
from app.services.catalog_unification import find_product_by_id_or_legacy
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

    def _product_by_ref(self, ref, *, field_name: str) -> Product:
        product = find_product_by_id_or_legacy(self.db, ref)
        if not product or not product.is_active:
            raise NotFoundError(f'Product not found for {field_name}')
        return product

    @staticmethod
    def _scale_engine_result(result: dict, multiplier: int) -> dict:
        """Multiply an engine result by a device count (draft routers ship qty
        N of the same assembly)."""
        multiplier = max(1, int(multiplier))
        if multiplier == 1:
            return result
        for line in result['lines']:
            line['qty'] = int(line['qty']) * multiplier
            line['line_total'] = line['unit_price'] * line['qty']
            line['monthly_total'] = line['monthly_unit'] * line['qty']
            line['one_time_total'] = line['one_time_unit'] * line['qty']
        result['one_time_total'] = result['one_time_total'] * multiplier
        result['monthly_total'] = result['monthly_total'] * multiplier
        return result

    def _primary_component(self, product: Product) -> ProductComponent:
        comps = sorted(
            (c for c in product.components if c.is_active),
            key=lambda c: (not c.is_required, c.component_type.value),
        )
        if not comps:
            raise AppError(f'Product {product.sku} has no active components', 400)
        return comps[0]

    # ── draft-solution (design flow) assembly, on the component engine ───────
    def _draft_groups(self, current_user: dict, draft_solution: dict) -> tuple[list[dict], str]:
        """Each draft router → a priced engine result (+ priced attached
        services). Returns (groups, currency)."""
        requirements = draft_solution.get('requirements') or {}
        routers = draft_solution.get('routers') or []
        if not routers:
            raise AppError('Draft solution must include at least one router', 400)

        num_sites = int(requirements.get('num_sites') or 1)
        currency = str(draft_solution.get('currency') or 'USD').upper()
        cps = ComponentPricingService(self.db)
        groups: list[dict] = []

        for index, router_input in enumerate(routers):
            product = self._product_by_ref(
                router_input.get('catalog_item_id') or router_input.get('product_id'),
                field_name='router.catalog_item_id',
            )
            router_qty = max(1, int(router_input.get('qty') or 1))
            result = cps.price_product(
                product.id, financial_model='CAPEX', interval='MONTH',
                selections={}, tenant_id=current_user['tenant_id'],
            )
            self._scale_engine_result(result, router_qty)

            services: list[dict] = []
            for service_index, service_input in enumerate(router_input.get('attached_services') or []):
                service_product = self._product_by_ref(
                    service_input.get('catalog_item_id') or service_input.get('product_id'),
                    field_name=f'router[{index}].attached_services[{service_index}].catalog_item_id',
                )
                service_attrs = service_product.attributes or {}
                allowed_categories = service_attrs.get('applies_to_categories') or []
                if allowed_categories and 'router' not in allowed_categories:
                    raise AppError('Selected service cannot be attached to a router', 400)
                pricing_basis = self._normalize_pricing_basis(
                    service_input.get('pricing_basis') or service_attrs.get('pricing_basis')
                )
                service_qty = self._service_quantity(
                    router_qty=router_qty,
                    requested_qty=service_input.get('qty'),
                    pricing_basis=pricing_basis,
                    num_sites=num_sites,
                )
                component = self._primary_component(service_product)
                service_result = cps.price_standalone_component(
                    component.id, qty=service_qty, financial_model='CAPEX',
                    interval='MONTH', tenant_id=current_user['tenant_id'],
                )
                services.append({
                    'product': service_product,
                    'result': service_result,
                    'metadata': {
                        'category': service_attrs.get('category'),
                        'service_kind': service_attrs.get('service_kind'),
                        'service_tier': service_attrs.get('tier'),
                        'pricing_basis': pricing_basis,
                        'router_product_id': str(product.id),
                    },
                })

            groups.append({
                'product': product,
                'result': result,
                'metadata': {
                    'category': (product.attributes or {}).get('category'),
                    'router_brand': (product.attributes or {}).get('brand'),
                    'router_model': (product.attributes or {}).get('model'),
                    'requirements': requirements,
                },
                'services': services,
            })

        return groups, currency

    # ── cart assembly (component lines only — Phase 7 WS4) ──────────────────
    def _cart_groups(self, current_user: dict) -> tuple[list[dict], str]:
        """Re-price the cart's component lines per tenant. Product lines are
        grouped back into {component_id: qty} selections; standalone lines are
        priced alone."""
        cart = self.cart_repo.get_or_create_active_cart(current_user['user_id'], current_user['tenant_id'])
        if not cart.lines:
            raise AppError('Cart is empty', 400)

        cps = ComponentPricingService(self.db)
        groups: list[dict] = []
        currency = cart.lines[0].currency if cart.lines else 'USD'

        legacy = [l for l in cart.lines if l.component_id is None]
        if legacy:
            raise AppError('Cart contains legacy items from before the catalog migration — please remove and re-add them', 409)

        standalone_lines = [l for l in cart.lines if (l.price_snapshot or {}).get('standalone')]
        grouped_lines = [l for l in cart.lines if not (l.price_snapshot or {}).get('standalone')]

        by_product: dict[str, dict] = {}
        for line in grouped_lines:
            snapshot = line.price_snapshot or {}
            key = str(line.product_id)
            group = by_product.setdefault(key, {'selections': {}, 'financial_model': None, 'cart_line_ids': []})
            group['selections'][str(line.component_id)] = line.quantity
            group['cart_line_ids'].append(str(line.id))
            if snapshot.get('is_parent') and snapshot.get('financial_model'):
                group['financial_model'] = snapshot['financial_model']

        for product_key, group in by_product.items():
            product = self.db.get(Product, self._parse_uuid(product_key, field_name='product_id'))
            if product is None or not product.is_active:
                raise NotFoundError('Cart contains an inactive or missing product')
            financial_model = self._resolve_financial_model(
                current_user, group['financial_model'] or 'CAPEX'
            )
            result = cps.price_product(
                product.id, financial_model=financial_model, interval='MONTH',
                selections=group['selections'], tenant_id=current_user['tenant_id'],
            )
            self._validate_requires_device(result)
            self._check_capacity(product, result)
            groups.append({
                'product': product,
                'result': result,
                'metadata': {'source_cart_line_ids': group['cart_line_ids']},
                'services': [],
            })

        for line in standalone_lines:
            component = self.db.get(ProductComponent, line.component_id)
            product = self.db.get(Product, line.product_id)
            if component is None or product is None:
                raise NotFoundError('Cart contains an inactive or missing component')
            result = cps.price_standalone_component(
                component.id, qty=line.quantity,
                financial_model=(line.price_snapshot or {}).get('financial_model') or 'CAPEX',
                interval='MONTH', tenant_id=current_user['tenant_id'],
            )
            groups.append({
                'product': product,
                'result': result,
                'metadata': {'standalone': True, 'source_cart_line_ids': [str(line.id)]},
                'services': [],
            })

        return groups, currency

    @staticmethod
    def _sum_group_totals(groups: list[dict]) -> tuple[Decimal, Decimal]:
        one_time = Decimal('0')
        monthly = Decimal('0')
        for group in groups:
            one_time += group['result']['one_time_total']
            monthly += group['result']['monthly_total']
            for service in group['services']:
                one_time += service['result']['one_time_total']
                monthly += service['result']['monthly_total']
        return one_time, monthly

    @staticmethod
    def _header_financial_model(groups: list[dict]) -> str:
        models = {group['result']['financial_model'] for group in groups}
        if len(models) == 1:
            return models.pop()
        return 'MIXED'

    def preview_quote(self, current_user: dict, draft_solution: dict) -> dict:
        self._assert_user_exists(current_user)
        # Gate deliberately checks the actor's home tenant: the whole quote/cart/
        # pricing write path is home-tenant-bound, so the gate must match the
        # tenant being written. Effective-tenant (X-Tenant-Id) threading for
        # quotes is a separate phase — see docs/plans/multi-tenant-config.md.
        if not self.onboarding_service.is_onboarding_complete(current_user['tenant_id']):
            raise AppError('Complete onboarding before creating a procurement request', 400)
        groups, currency = self._draft_groups(current_user, draft_solution)
        one_time_total, monthly_total = self._sum_group_totals(groups)
        projected = self.pricing_service._quantize_money(one_time_total + monthly_total * Decimal('12'))
        self.db.commit()

        return {
            'one_time_total': float(self.pricing_service._quantize_money(one_time_total)),
            'monthly_total': float(self.pricing_service._quantize_money(monthly_total)),
            'projected_12_month_cost': float(projected),
            'currency': currency,
            'default_discount_pct': 0.0,
            'incremental_discount_pct': 0.0,
        }

    def create_quote(self, current_user: dict, payload: dict | None = None):
        self._assert_user_exists(current_user)
        if not self.onboarding_service.is_onboarding_complete(current_user['tenant_id']):
            raise AppError('Complete onboarding before creating a procurement request', 400)

        if payload and payload.get('draft_solution'):
            groups, currency = self._draft_groups(current_user, payload['draft_solution'])
        else:
            groups, currency = self._cart_groups(current_user)

        one_time_total, monthly_total = self._sum_group_totals(groups)
        one_time_total = self.pricing_service._quantize_money(one_time_total)
        monthly_total = self.pricing_service._quantize_money(monthly_total)
        projected_12_month_cost = self.pricing_service._quantize_money(
            one_time_total + monthly_total * Decimal('12')
        )

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

        for group in groups:
            line_ids = self._write_component_lines(
                quote, group['product'], group['result'], group['result']['financial_model'],
                extra_metadata=group['metadata'],
            )
            parent_line_id = None
            device_line = next(
                (l for l in group['result']['lines'] if l['component_type'] == ComponentType.DEVICE.value),
                None,
            )
            if device_line is not None:
                parent_line_id = line_ids.get(device_line['component_id'])
            for service in group['services']:
                self._write_component_lines(
                    quote, service['product'], service['result'], service['result']['financial_model'],
                    extra_metadata=service['metadata'], parent_line_id=parent_line_id,
                )
        quote.financial_model = self._header_financial_model(groups)
        quote.subscription_interval = 'MONTH'

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
            quote_public_id=quote.public_id,
            source='draft_solution' if (payload and payload.get('draft_solution')) else 'cart',
            design_id=design_id,
            line_count=sum(
                len(g['result']['lines']) + sum(len(s['result']['lines']) for s in g['services'])
                for g in groups
            ),
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
        """Block over-subscription of a device's capacity (§5, block + warn).
        Capacity scales with the device count (qty 2 devices → 16 FXS ports)."""
        from sqlalchemy import select
        comp_ids = [self._parse_uuid(l['component_id'], field_name='component_id') for l in result['lines']]
        if not comp_ids:
            return
        comps = {
            str(c.id): c
            for c in self.db.scalars(select(ProductComponent).where(ProductComponent.id.in_(comp_ids)))
        }
        device_qty = next(
            (int(l['qty']) for l in result['lines'] if l['component_type'] == ComponentType.DEVICE.value), 1
        )
        provided = {
            k: v * max(1, device_qty)
            for k, v in ((product.attributes or {}).get('capacity') or {}).items()
        }
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

    def _component_line_kwargs(self, quote_id, product, financial_model, result, line, parent_line_id,
                               extra_metadata: dict | None = None):
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
                **(extra_metadata or {}),
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

    def _write_component_lines(self, quote, product, result, financial_model,
                               extra_metadata: dict | None = None,
                               parent_line_id=None) -> dict[str, str]:
        """Append one product's computed tree to a quote (device parent first).
        Returns {component_id: quote_line_id} so callers can attach follow-on
        lines (e.g. draft-solution managed services) under the device."""
        ordered = sorted(result['lines'], key=lambda l: 0 if l['component_type'] == ComponentType.DEVICE.value else 1)
        quote_line_id_by_component_id: dict[str, str] = {}
        for line in ordered:
            line_parent_id = parent_line_id
            parent_cid = line.get('parent_component_id')
            if parent_cid:
                line_parent_id = quote_line_id_by_component_id.get(parent_cid) or parent_line_id
            created = self.quote_repo.add_line(
                **self._component_line_kwargs(
                    quote.id, product, financial_model, result, line, line_parent_id,
                    extra_metadata=extra_metadata,
                )
            )
            quote_line_id_by_component_id[line['component_id']] = str(created.id)
        return quote_line_id_by_component_id

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
            quote_public_id=quote.public_id,
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
            quote_public_id=quote.public_id,
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
        # BUG-AUD-009: financial reconciliation needs the public order id and the
        # dollar amounts. The Order has no total column; the figures live on the
        # source quote (one-time + monthly).
        one_time_total = float(quote.one_time_total)
        monthly_total = float(quote.monthly_total)
        audit.log('quote_converted', quote_id=quote_id_text, quote_public_id=quote.public_id,
                  order_id=order_id, order_public_id=order.public_id, line_count=line_count,
                  total_amount=one_time_total, monthly_total=monthly_total)
        audit.log('order_placed', order_id=order_id, order_public_id=order.public_id,
                  quote_id=quote_id_text, line_count=line_count,
                  financial_model=order.financial_model,
                  total_amount=one_time_total, monthly_total=monthly_total)
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
