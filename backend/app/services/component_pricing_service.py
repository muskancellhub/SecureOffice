"""Component pricing engine (Secure Office, Phase 2; per-tenant rules Phase 7).

Computes CAPEX / OPEX prices for products assembled from product_components.
Pinned worked example (Phase 7 D6): a 90X1 OPEX 36-mo quote with one voice line
+ SIM for a 20%-margin tenant resolves to $42.88/mo (lease 19.78 + controller
9.30 + line 13.80) plus a $30 one-time SIM.

Phase 7 (one catalog): this engine prices EVERY sellable surface. Margin
precedence is D2 — override (tenant+SKU) → customer_pricing.default_margin_pct
(tenant-wide, nullable) → products.margin_pct → component margin → 25% global.
PAPI-sourced products resell at PAPI's exact price (zero margin, read-only, D8).
See docs/plans/phase-2-pricing-engine.md and phase-7.
"""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.core.tenancy import CELLHUB_MASTER_TENANT_ID
from app.models.financing import FinancingTerms
from app.models.pricing import CustomerPricing
from app.models.product import (
    ComponentType,
    CustomerPriceOverride,
    Product,
    ProductComponent,
)

MONEY_QUANT = Decimal('0.01')
PCT_QUANT = Decimal('0.0001')
MONTHS_PER_YEAR = Decimal('12')

# Under OPEX, only *hardware* one-time components are financed into a lease MRC;
# install / professional-services stay one-time even under OPEX.
FINANCEABLE_TYPES = {ComponentType.DEVICE, ComponentType.ACCESSORY}
# Components billed at a flat final price with NO margin applied (SIM, D6).
FLAT_PRICE_TYPES = {ComponentType.SIM, ComponentType.BACKUP_SIM}
# Final fallback when no override / tenant default / SKU / component margin is
# set (Phase 7 D2/D7).
GLOBAL_DEFAULT_MARGIN = Decimal('0.25')


def is_papi_product(product: Product) -> bool:
    """PAPI-sourced products resell at PAPI's exact price — zero margin,
    not editable (Phase 7 D8). SIM components are exempt (D6) but PAPI
    devices never carry one."""
    attrs = product.attributes or {}
    return str(attrs.get('source_type') or '').lower() == 'paapi' or (product.vendor or '').strip().upper() == 'PAPI'


def _d(value, *, fallback: Decimal = Decimal('0')) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return fallback


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


class ComponentPricingService:
    def __init__(self, db: Session):
        self.db = db

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _parse_uuid(value, *, field_name: str) -> uuid.UUID:
        try:
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except (TypeError, ValueError):
            raise AppError(f'Invalid {field_name}', 400)

    @staticmethod
    def lease_mrc(principal: Decimal, annual_rate: Decimal, term_months: int) -> Decimal:
        """Amortizing annuity (PMT). 660 @ 5% / 36 -> 19.78 (rounded only here)."""
        if term_months <= 0:
            raise AppError('term_months must be > 0', 422)
        if annual_rate <= 0:
            return _money(principal / Decimal(term_months))
        r = annual_rate / MONTHS_PER_YEAR
        factor = Decimal('1') - (Decimal('1') + r) ** (-term_months)
        return _money(principal * r / factor)

    def _resolve_override(self, tenant_id, *, product_id, component_id) -> CustomerPriceOverride | None:
        if tenant_id is None:
            return None
        tid = self._parse_uuid(tenant_id, field_name='tenant_id')
        # Component-specific override wins over product-level.
        row = self.db.scalar(
            select(CustomerPriceOverride).where(
                CustomerPriceOverride.tenant_id == tid,
                CustomerPriceOverride.component_id == component_id,
            )
        )
        if row:
            return row
        return self.db.scalar(
            select(CustomerPriceOverride).where(
                CustomerPriceOverride.tenant_id == tid,
                CustomerPriceOverride.product_id == product_id,
                CustomerPriceOverride.component_id.is_(None),
            )
        )

    def _resolve_margin(self, component, product, override, customer_pricing) -> tuple[Decimal, str]:
        """Markup-on-cost precedence (Phase 7 D2, locked).

        override_margin_pct (per-tenant per-SKU/component)
          -> customer_pricing.default_margin_pct (tenant-wide; nullable, null = inherit)
          -> products.margin_pct                 (SKU default)
          -> product_components.margin_pct       (per-component baseline)
          -> GLOBAL_DEFAULT_MARGIN (25%)

        The tenant-wide default became nullable in Phase 7 so "tenant hasn't
        customized" is distinguishable from a real 0%.
        """
        if override is not None and override.override_margin_pct is not None:
            return _d(override.override_margin_pct), 'override_margin_pct'
        if customer_pricing is not None and customer_pricing.default_margin_pct is not None:
            return _d(customer_pricing.default_margin_pct), 'customer.default_margin_pct'
        if product.margin_pct is not None:
            return _d(product.margin_pct), 'product.margin_pct'
        if component.margin_pct is not None:
            return _d(component.margin_pct), 'component.margin_pct'
        return GLOBAL_DEFAULT_MARGIN, 'global_default'

    def _default_financing(self, tenant_id=None) -> FinancingTerms | None:
        """The active default term for ``tenant_id`` (multi-tenant Phase 1).

        Falls back to the CellHub master tenant's default when the tenant has no
        financing of its own (legacy tenants created before clone-on-onboard), so
        pricing never breaks while per-tenant financing is being populated.
        """
        def _q(tid):
            return self.db.scalar(
                select(FinancingTerms).where(
                    FinancingTerms.is_default.is_(True),
                    FinancingTerms.is_active.is_(True),
                    FinancingTerms.tenant_id == tid,
                )
            )

        master = uuid.UUID(CELLHUB_MASTER_TENANT_ID)
        if tenant_id is not None:
            tid = self._parse_uuid(tenant_id, field_name='tenant_id')
            return _q(tid) or _q(master)
        return _q(master)

    # ── per-component pricing ────────────────────────────────────────────────
    def price_component(
        self,
        component: ProductComponent,
        *,
        product: Product,
        financial_model: str,
        interval: str,
        qty: int,
        customer_pricing: CustomerPricing | None = None,
        override: CustomerPriceOverride | None = None,
        annual_rate: Decimal | None = None,
        term_months: int | None = None,
    ) -> dict:
        financial_model = (financial_model or 'CAPEX').upper()
        interval = (interval or 'MONTH').upper()
        qty = int(qty)

        is_flat = component.component_type in FLAT_PRICE_TYPES or bool((component.attributes or {}).get('flat_price'))
        is_one_time = component.billing == 'ONE_TIME'
        # PAPI zero-margin (D8): resell at PAPI's exact cost; markup AND
        # overrides are ignored. SIM/flat components are exempt (D6) so a
        # tenant-priced SIM (override_unit_price) still works.
        papi_locked = is_papi_product(product) and not is_flat

        # Resolve the pre-cadence unit base (cost * (1+margin)), honoring overrides.
        if papi_locked:
            unit_base = _d(component.vendor_cost)
            margin, margin_source = Decimal('0'), 'papi_fixed'
        elif override is not None and override.override_unit_price is not None:
            unit_base = _d(override.override_unit_price)
            margin, margin_source = Decimal('0'), 'override_unit_price'
        elif is_flat:
            unit_base = _d(component.vendor_cost)
            margin, margin_source = Decimal('0'), 'flat_price'
        else:
            margin, margin_source = self._resolve_margin(component, product, override, customer_pricing)
            unit_base = _d(component.vendor_cost) * (Decimal('1') + margin)

        financed = False
        one_time_unit = Decimal('0')
        monthly_unit = Decimal('0')

        if is_one_time and financial_model == 'OPEX' and component.component_type in FINANCEABLE_TYPES:
            # Hardware financed into a monthly lease (amortizing annuity).
            rate = _d(product.leasing_pct) if product.leasing_pct is not None else _d(annual_rate, fallback=Decimal('0.05'))
            term = term_months or 36
            monthly_unit = self.lease_mrc(unit_base, rate, term)
            financed = True
        elif is_one_time:
            one_time_unit = _money(unit_base)
        else:
            # Recurring component (controller, line, managed service, SIM, ...).
            monthly_unit = _money(unit_base)

        # Display amount at the chosen interval (annual = monthly x 12).
        period_mult = MONTHS_PER_YEAR if interval == 'YEAR' else Decimal('1')
        if financed or not is_one_time:
            display_unit = _money(monthly_unit * period_mult)
            billing = 'RECURRING'
            eff_interval = interval
        else:
            display_unit = one_time_unit
            billing = 'ONE_TIME'
            eff_interval = None

        return {
            'component_id': str(component.id),
            'component_type': component.component_type.value,
            'label': component.label,
            'vendor_component_sku': component.vendor_component_sku,
            'qty': qty,
            'vendor_cost': _d(component.vendor_cost),
            'margin_pct': margin,
            'margin_source': margin_source,
            'price_editable': not papi_locked,
            'billing': billing,
            'interval': eff_interval,
            'financed': financed,
            'unit_price': display_unit,            # per-unit at the chosen cadence
            'monthly_unit': monthly_unit,          # monthly MRC (0 for one-time non-financed)
            'one_time_unit': one_time_unit,        # one-time sell (0 for recurring/financed)
            'line_total': _money(display_unit * qty),
            'monthly_total': _money(monthly_unit * qty),
            'one_time_total': _money(one_time_unit * qty),
        }

    # ── product-level assembly ───────────────────────────────────────────────
    def price_product(
        self,
        product_id,
        *,
        financial_model: str = 'CAPEX',
        interval: str = 'MONTH',
        selections: dict | None = None,
        tenant_id=None,
    ) -> dict:
        """Build the priced line tree for one product.

        selections: {component_id: qty}. Required active components are always
        included (default_qty unless overridden); optional components are included
        only when present in selections with qty > 0.
        """
        financial_model = (financial_model or 'CAPEX').upper()
        interval = (interval or 'MONTH').upper()
        if financial_model not in ('CAPEX', 'OPEX'):
            raise AppError("financial_model must be CAPEX or OPEX", 422)
        if interval not in ('MONTH', 'YEAR'):
            raise AppError("interval must be MONTH or YEAR", 422)
        selections = {str(k): int(v) for k, v in (selections or {}).items()}

        pid = self._parse_uuid(product_id, field_name='product_id')
        product = self.db.get(Product, pid)
        if product is None or not product.is_active:
            raise NotFoundError('Product not found')

        components = self.db.scalars(
            select(ProductComponent).where(
                ProductComponent.product_id == product.id,
                ProductComponent.is_active.is_(True),
            )
        ).all()

        customer_pricing = None
        if tenant_id is not None:
            customer_pricing = self.db.get(CustomerPricing, self._parse_uuid(tenant_id, field_name='tenant_id'))

        financing = self._default_financing(tenant_id)
        annual_rate = _d(financing.annual_rate_pct) if financing else Decimal('0.05')
        term_months = financing.term_months if financing else 36

        priced_lines = []
        device_line = None
        for c in components:
            # financial-model eligibility: component must allow the requested model.
            if c.financial_model not in ('BOTH', financial_model):
                continue
            cid = str(c.id)
            if c.is_required:
                qty = selections.get(cid, c.default_qty)
            else:
                if cid not in selections or selections[cid] <= 0:
                    continue
                qty = selections[cid]
            if qty <= 0:
                continue
            override = self._resolve_override(tenant_id, product_id=product.id, component_id=c.id)
            line = self.price_component(
                c, product=product, financial_model=financial_model, interval=interval,
                qty=qty, customer_pricing=customer_pricing, override=override,
                annual_rate=annual_rate, term_months=term_months,
            )
            if c.component_type == ComponentType.DEVICE:
                device_line = line
            priced_lines.append(line)

        # Parent/child tree: the DEVICE line is the parent; everything else hangs off it.
        parent_id = device_line['component_id'] if device_line else None
        for line in priced_lines:
            line['parent_component_id'] = None if line is device_line else parent_id

        one_time_total = sum((l['one_time_total'] for l in priced_lines), Decimal('0'))
        monthly_total = sum((l['monthly_total'] for l in priced_lines), Decimal('0'))
        period_mult = MONTHS_PER_YEAR if interval == 'YEAR' else Decimal('1')
        recurring_total_at_interval = _money(monthly_total * period_mult)
        projected_term_cost = _money(one_time_total + monthly_total * Decimal(term_months))

        return {
            'product': {
                'id': str(product.id),
                'sku': product.sku,
                'name': product.name,
                'vendor': product.vendor,
            },
            'financial_model': financial_model,
            'interval': interval,
            'term_months': term_months,
            'annual_rate_pct': annual_rate,
            'price_editable': not is_papi_product(product),
            'lines': priced_lines,
            'one_time_total': _money(one_time_total),
            'monthly_total': _money(monthly_total),
            'recurring_total_at_interval': recurring_total_at_interval,
            'projected_term_cost': projected_term_cost,
        }

    # ── standalone components (à-la-carte, Phase 7 D10) ─────────────────────
    def price_standalone_component(
        self,
        component_id,
        *,
        qty: int = 1,
        financial_model: str = 'CAPEX',
        interval: str = 'MONTH',
        tenant_id=None,
    ) -> dict:
        """Price ONE component without its product's required tree — "add one
        more line" / "buy just a SIM" / "router only". The caller is responsible
        for the requires-a-device / capacity validation."""
        cid = self._parse_uuid(component_id, field_name='component_id')
        component = self.db.get(ProductComponent, cid)
        if component is None or not component.is_active:
            raise NotFoundError('Component not found')
        product = self.db.get(Product, component.product_id)
        if product is None or not product.is_active:
            raise NotFoundError('Product not found')

        financial_model = (financial_model or 'CAPEX').upper()
        interval = (interval or 'MONTH').upper()
        qty = int(qty)
        if qty <= 0:
            raise AppError('qty must be > 0', 422)

        customer_pricing = None
        if tenant_id is not None:
            customer_pricing = self.db.get(CustomerPricing, self._parse_uuid(tenant_id, field_name='tenant_id'))
        financing = self._default_financing(tenant_id)
        annual_rate = _d(financing.annual_rate_pct) if financing else Decimal('0.05')
        term_months = financing.term_months if financing else 36
        override = self._resolve_override(tenant_id, product_id=product.id, component_id=component.id)

        line = self.price_component(
            component, product=product, financial_model=financial_model, interval=interval,
            qty=qty, customer_pricing=customer_pricing, override=override,
            annual_rate=annual_rate, term_months=term_months,
        )
        line['parent_component_id'] = None
        return {
            'product': {
                'id': str(product.id),
                'sku': product.sku,
                'name': product.name,
                'vendor': product.vendor,
            },
            'financial_model': financial_model,
            'interval': interval,
            'term_months': term_months,
            'annual_rate_pct': annual_rate,
            'price_editable': line['price_editable'],
            'lines': [line],
            'one_time_total': line['one_time_total'],
            'monthly_total': line['monthly_total'],
        }

    # ── bulk catalog pricing (Phase 7 WS3 — customer catalog reads) ──────────
    def price_catalog_entries(self, products: list[Product], *, tenant_id=None) -> dict[str, dict]:
        """Headline per-tenant pricing for a page of products, batched.

        Returns {product_id: {'one_time_price', 'monthly_price',
        'managed_service_monthly', 'price_editable', 'billing'}} computed from
        required components (CAPEX headline + recurring $/mo) plus the priced
        MANAGED_SERVICE component, even when optional. One query per table —
        never one per product.
        """
        if not products:
            return {}
        product_ids = [p.id for p in products]
        components = self.db.scalars(
            select(ProductComponent).where(
                ProductComponent.product_id.in_(product_ids),
                ProductComponent.is_active.is_(True),
            )
        ).all()

        customer_pricing = None
        overrides_by_component: dict = {}
        overrides_by_product: dict = {}
        if tenant_id is not None:
            tid = self._parse_uuid(tenant_id, field_name='tenant_id')
            customer_pricing = self.db.get(CustomerPricing, tid)
            for o in self.db.scalars(
                select(CustomerPriceOverride).where(CustomerPriceOverride.tenant_id == tid)
            ):
                if o.component_id is not None:
                    overrides_by_component[o.component_id] = o
                elif o.product_id is not None:
                    overrides_by_product[o.product_id] = o

        financing = self._default_financing(tenant_id)
        annual_rate = _d(financing.annual_rate_pct) if financing else Decimal('0.05')
        term_months = financing.term_months if financing else 36

        by_product: dict = {p.id: p for p in products}
        result: dict[str, dict] = {
            str(p.id): {
                'one_time_price': Decimal('0'),
                'monthly_price': Decimal('0'),
                'managed_service_monthly': None,
                'price_editable': not is_papi_product(p),
            }
            for p in products
        }
        for c in components:
            product = by_product.get(c.product_id)
            if product is None:
                continue
            override = overrides_by_component.get(c.id) or overrides_by_product.get(c.product_id)
            entry = result[str(c.product_id)]
            if c.component_type == ComponentType.MANAGED_SERVICE and entry['managed_service_monthly'] is None:
                ms_line = self.price_component(
                    c, product=product, financial_model='CAPEX', interval='MONTH',
                    qty=1, customer_pricing=customer_pricing, override=override,
                    annual_rate=annual_rate, term_months=term_months,
                )
                entry['managed_service_monthly'] = ms_line['monthly_unit']
            if not c.is_required:
                continue
            line = self.price_component(
                c, product=product, financial_model='CAPEX', interval='MONTH',
                qty=c.default_qty, customer_pricing=customer_pricing, override=override,
                annual_rate=annual_rate, term_months=term_months,
            )
            entry['one_time_price'] += line['one_time_total']
            entry['monthly_price'] += line['monthly_total']

        for entry in result.values():
            entry['one_time_price'] = _money(entry['one_time_price'])
            entry['monthly_price'] = _money(entry['monthly_price'])
        return result
