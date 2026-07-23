"""Admin CRUD for the component catalog (Secure Office, Phase 4).

Products / components / financing terms / customer commercial config / price
overrides — every field that feeds ComponentPricingService is editable here, so
the portal needs no spreadsheet (spec §9, §13). Edits take effect on the next
preview/quote because the engine reads these tables live.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppError, NotFoundError
from app.models.financing import FinancingTerms
from app.models.pricing import CustomerPricing
from app.models.product import (
    Bundle,
    BundleItem,
    ComponentType,
    ComponentUom,
    CustomerPriceOverride,
    FinancialModel,
    Product,
    ProductComponent,
)
from app.services.audit_logger import audit

_COMPONENT_TYPES = {e.value for e in ComponentType}
_UOMS = {e.value for e in ComponentUom}
_FINANCIAL_MODELS = {e.value for e in FinancialModel}
_BILLINGS = {'ONE_TIME', 'RECURRING'}
_INTERVALS = {'MONTH', 'YEAR'}
_CREDIT_STATUSES = {'PENDING', 'PASS', 'FAIL'}


def _dec(value):
    return None if value is None else Decimal(str(value))


class ProductAdminService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _parse_uuid(value, *, field_name: str) -> uuid.UUID:
        try:
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except (TypeError, ValueError):
            raise AppError(f'Invalid {field_name}', 400)

    # ── products ─────────────────────────────────────────────────────────────
    def list_products(self, *, vendor=None, technology=None, financial_model=None, is_active=None) -> list[Product]:
        stmt = select(Product).options(selectinload(Product.components))
        if vendor:
            stmt = stmt.where(Product.vendor == vendor)
        if technology:
            stmt = stmt.where(Product.technology == technology)
        if financial_model:
            stmt = stmt.where(Product.default_financial_model == financial_model)
        if is_active is not None:
            stmt = stmt.where(Product.is_active.is_(is_active))
        return list(self.db.scalars(stmt.order_by(Product.vendor, Product.technology, Product.sku)).all())

    def get_product(self, product_id) -> Product:
        product = self.db.scalar(
            select(Product).where(Product.id == self._parse_uuid(product_id, field_name='product_id'))
            .options(selectinload(Product.components))
        )
        if product is None:
            raise NotFoundError('Product not found')
        return product

    def create_product(self, payload: dict) -> Product:
        product = self._build_product(payload)
        self.db.add(product)
        self.db.commit()
        audit.log('product_created', product_id=str(product.id), sku=product.sku,
                  vendor=product.vendor, technology=product.technology, name=product.name)
        return self.get_product(product.id)

    def _build_product(self, payload: dict) -> Product:
        """Validate product fields + SKU uniqueness and return an unsaved Product.
        Shared by create_product and create_product_with_components."""
        for field in ('vendor', 'technology', 'sku', 'name'):
            if not (payload.get(field) or '').strip():
                raise AppError(f'{field} is required', 400)
        if self.db.scalar(select(Product).where(Product.sku == payload['sku'])):
            raise AppError(f"Product sku '{payload['sku']}' already exists", 409)
        fm = payload.get('default_financial_model', 'BOTH')
        if fm not in _FINANCIAL_MODELS:
            raise AppError('Invalid default_financial_model', 422)
        return Product(
            vendor=payload['vendor'], technology=payload['technology'], sku=payload['sku'],
            vendor_sku=payload.get('vendor_sku'), name=payload['name'],
            description=payload.get('description'), default_financial_model=fm,
            margin_pct=_dec(payload.get('margin_pct')), leasing_pct=_dec(payload.get('leasing_pct')),
            is_active=payload.get('is_active', True), attributes=payload.get('attributes') or {},
        )

    def _build_component(self, product_id, payload: dict) -> ProductComponent:
        """Validate + return an unsaved ProductComponent for the given product."""
        self._validate_component_fields(payload, partial=False)
        return ProductComponent(
            product_id=product_id,
            component_type=payload['component_type'],
            financial_model=payload.get('financial_model', 'BOTH'),
            label=payload['label'],
            vendor_component_sku=payload.get('vendor_component_sku'),
            vendor_cost=_dec(payload['vendor_cost']),
            msrp=_dec(payload.get('msrp')),
            uom=payload.get('uom', 'PER_DEVICE'),
            billing=payload.get('billing', 'ONE_TIME'),
            interval=payload.get('interval'),
            margin_pct=_dec(payload.get('margin_pct')),
            leasing_pct=_dec(payload.get('leasing_pct')),
            default_qty=payload.get('default_qty', 1),
            is_required=payload.get('is_required', True),
            is_active=payload.get('is_active', True),
            attributes=payload.get('attributes') or {},
        )

    def create_product_with_components(self, product_payload: dict, components: list[dict]) -> Product:
        """BUG-PRODUCT-DATA-004: create a product and all its components in ONE
        transaction. Everything is validated BEFORE anything is added, and a
        single commit persists it all — so an invalid component never leaves an
        orphaned product (and its SKU free to retry) behind.
        """
        if not components:
            raise AppError('At least one component is required', 400)
        # Validate the product first, then every component — annotating which
        # component failed — with NOTHING written to the DB yet.
        product = self._build_product(product_payload)
        built_components = []
        for idx, comp_payload in enumerate(components):
            try:
                built_components.append(self._build_component(None, comp_payload))
            except AppError as err:
                raise AppError(f'Component {idx + 1}: {err.message}', err.status_code)

        # All valid — persist atomically.
        self.db.add(product)
        self.db.flush()  # assign product.id (and surface a unique-SKU race here)
        for component in built_components:
            component.product_id = product.id
            self.db.add(component)
        self.db.commit()
        audit.log('product_created', product_id=str(product.id), sku=product.sku,
                  vendor=product.vendor, technology=product.technology, name=product.name,
                  component_count=len(built_components), atomic=True)
        return self.get_product(product.id)

    def update_product(self, product_id, payload: dict) -> Product:
        product = self.get_product(product_id)
        if 'default_financial_model' in payload and payload['default_financial_model'] not in _FINANCIAL_MODELS:
            raise AppError('Invalid default_financial_model', 422)
        for field in ('vendor', 'technology', 'name', 'description', 'vendor_sku',
                      'default_financial_model', 'is_active', 'attributes'):
            if field in payload:
                setattr(product, field, payload[field])
        for field in ('margin_pct', 'leasing_pct'):
            if field in payload:
                setattr(product, field, _dec(payload[field]))
        self.db.commit()
        audit.log('product_updated', product_id=str(product.id), sku=product.sku,
                  fields_changed=sorted(payload.keys()))
        return self.get_product(product.id)

    # ── components ───────────────────────────────────────────────────────────
    @staticmethod
    def _validate_component_fields(payload: dict, *, partial: bool) -> None:
        if not partial:
            if payload.get('component_type') not in _COMPONENT_TYPES:
                raise AppError('Invalid component_type', 422)
            if not (payload.get('label') or '').strip():
                raise AppError('label is required', 400)
            if payload.get('vendor_cost') is None:
                raise AppError('vendor_cost is required', 400)
        else:
            if 'component_type' in payload and payload['component_type'] not in _COMPONENT_TYPES:
                raise AppError('Invalid component_type', 422)
        if payload.get('uom') is not None and payload['uom'] not in _UOMS:
            raise AppError('Invalid uom', 422)
        if payload.get('financial_model') is not None and payload['financial_model'] not in _FINANCIAL_MODELS:
            raise AppError('Invalid financial_model', 422)
        if payload.get('billing') is not None and payload['billing'] not in _BILLINGS:
            raise AppError('Invalid billing', 422)
        if payload.get('interval') is not None and payload['interval'] not in _INTERVALS:
            raise AppError('Invalid interval', 422)

    def add_component(self, product_id, payload: dict) -> ProductComponent:
        product = self.get_product(product_id)
        self._validate_component_fields(payload, partial=False)
        component = ProductComponent(
            product_id=product.id,
            component_type=payload['component_type'],
            financial_model=payload.get('financial_model', 'BOTH'),
            label=payload['label'],
            vendor_component_sku=payload.get('vendor_component_sku'),
            vendor_cost=_dec(payload['vendor_cost']),
            msrp=_dec(payload.get('msrp')),
            uom=payload.get('uom', 'PER_DEVICE'),
            billing=payload.get('billing', 'ONE_TIME'),
            interval=payload.get('interval'),
            margin_pct=_dec(payload.get('margin_pct')),
            leasing_pct=_dec(payload.get('leasing_pct')),
            default_qty=payload.get('default_qty', 1),
            is_required=payload.get('is_required', True),
            is_active=payload.get('is_active', True),
            attributes=payload.get('attributes') or {},
        )
        self.db.add(component)
        self.db.commit()
        self.db.refresh(component)
        audit.log('component_created', component_id=str(component.id),
                  product_id=str(product.id), component_type=component.component_type,
                  label=component.label)
        return component

    def update_component(self, component_id, payload: dict) -> ProductComponent:
        component = self.db.get(ProductComponent, self._parse_uuid(component_id, field_name='component_id'))
        if component is None:
            raise NotFoundError('Component not found')
        self._validate_component_fields(payload, partial=True)
        for field in ('component_type', 'financial_model', 'label', 'vendor_component_sku',
                      'uom', 'billing', 'interval', 'default_qty', 'is_required', 'is_active', 'attributes'):
            if field in payload:
                setattr(component, field, payload[field])
        for field in ('vendor_cost', 'msrp', 'margin_pct', 'leasing_pct'):
            if field in payload:
                setattr(component, field, _dec(payload[field]))
        self.db.commit()
        self.db.refresh(component)
        audit.log('component_updated', component_id=str(component.id),
                  product_id=str(component.product_id), fields_changed=sorted(payload.keys()))
        return component

    # ── financing terms (per-tenant, multi-tenant Phase 1) ───────────────────
    def _financing_for_tenant(self, tenant_id):
        """Base SELECT scoped to one tenant. Single source of the tenant filter so
        no financing query can accidentally span tenants."""
        tid = self._parse_uuid(tenant_id, field_name='tenant_id')
        return tid, select(FinancingTerms).where(FinancingTerms.tenant_id == tid)

    def list_financing_terms(self, tenant_id) -> list[FinancingTerms]:
        _, stmt = self._financing_for_tenant(tenant_id)
        return list(self.db.scalars(stmt.order_by(FinancingTerms.term_months)).all())

    def create_financing_terms(self, tenant_id, payload: dict) -> FinancingTerms:
        if not (payload.get('name') or '').strip():
            raise AppError('name is required', 400)
        tid, stmt = self._financing_for_tenant(tenant_id)
        is_default = bool(payload.get('is_default'))
        if is_default:
            for row in self.db.scalars(stmt.where(FinancingTerms.is_default.is_(True))):
                row.is_default = False
        term = FinancingTerms(
            tenant_id=tid,
            name=payload['name'],
            term_months=payload.get('term_months', 36),
            annual_rate_pct=_dec(payload.get('annual_rate_pct', '0.0500')),
            subscription_interval=payload.get('subscription_interval', 'MONTH'),
            is_default=is_default,
            is_active=payload.get('is_active', True),
        )
        self.db.add(term)
        self.db.commit()
        self.db.refresh(term)
        audit.log('financing_terms_created', financing_terms_id=str(term.id),
                  target_tenant_id=str(tid), name=term.name,
                  term_months=term.term_months, annual_rate_pct=float(term.annual_rate_pct),
                  is_default=term.is_default)
        return term

    # ── customer commercial config ───────────────────────────────────────────
    def update_customer_commercial(self, tenant_id, payload: dict) -> CustomerPricing:
        tid = self._parse_uuid(tenant_id, field_name='tenant_id')
        pricing = self.db.get(CustomerPricing, tid)
        if pricing is None:
            pricing = CustomerPricing(tenant_id=tid)
            self.db.add(pricing)
        if 'credit_status' in payload and payload['credit_status'] not in _CREDIT_STATUSES:
            raise AppError('Invalid credit_status', 422)
        if 'default_margin_pct' in payload:
            pricing.default_margin_pct = _dec(payload['default_margin_pct'])
        if 'opex_eligible' in payload:
            pricing.opex_eligible = bool(payload['opex_eligible'])
        if 'credit_status' in payload:
            pricing.credit_status = payload['credit_status']
        if 'credit_limit' in payload:
            pricing.credit_limit = _dec(payload['credit_limit'])
        self.db.commit()
        self.db.refresh(pricing)
        audit.log('customer_commercial_changed', target_tenant_id=str(tid),
                  fields_changed=sorted(payload.keys()),
                  credit_status=pricing.credit_status, opex_eligible=pricing.opex_eligible)
        return pricing

    # ── bundles (Phase 5) ────────────────────────────────────────────────────
    def list_bundles(self) -> list[Bundle]:
        return list(self.db.scalars(
            select(Bundle).options(selectinload(Bundle.items)).order_by(Bundle.sku)
        ).all())

    def get_bundle(self, bundle_id) -> Bundle:
        bundle = self.db.scalar(
            select(Bundle).where(Bundle.id == self._parse_uuid(bundle_id, field_name='bundle_id'))
            .options(selectinload(Bundle.items))
        )
        if bundle is None:
            raise NotFoundError('Bundle not found')
        return bundle

    def create_bundle(self, payload: dict) -> Bundle:
        for field in ('sku', 'name'):
            if not (payload.get(field) or '').strip():
                raise AppError(f'{field} is required', 400)
        if self.db.scalar(select(Bundle).where(Bundle.sku == payload['sku'])):
            raise AppError(f"Bundle sku '{payload['sku']}' already exists", 409)
        bundle = Bundle(
            sku=payload['sku'], name=payload['name'], vendor=payload.get('vendor'),
            technology=payload.get('technology'), description=payload.get('description'),
            is_active=payload.get('is_active', True), attributes=payload.get('attributes') or {},
        )
        self.db.add(bundle)
        self.db.commit()
        audit.log('bundle_created', bundle_id=str(bundle.id), sku=bundle.sku,
                  name=bundle.name, vendor=bundle.vendor)
        return self.get_bundle(bundle.id)

    def add_bundle_item(self, bundle_id, payload: dict) -> BundleItem:
        bundle = self.get_bundle(bundle_id)
        product_id = payload.get('product_id')
        if not product_id:
            raise AppError('product_id is required', 400)
        product_uuid = self._parse_uuid(product_id, field_name='product_id')
        if self.db.get(Product, product_uuid) is None:
            raise NotFoundError('Product not found')
        item = BundleItem(
            bundle_id=bundle.id, product_id=product_uuid,
            default_qty=payload.get('default_qty', 1),
            is_optional=payload.get('is_optional', False),
            is_removable=payload.get('is_removable', True),
            sort_order=payload.get('sort_order', 0),
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        audit.log('bundle_item_added', bundle_id=str(bundle.id),
                  product_id=str(product_uuid), default_qty=item.default_qty,
                  is_optional=item.is_optional)
        return item

    def upsert_price_override(self, tenant_id, payload: dict) -> CustomerPriceOverride:
        tid = self._parse_uuid(tenant_id, field_name='tenant_id')
        product_id = payload.get('product_id')
        component_id = payload.get('component_id')
        if not product_id and not component_id:
            raise AppError('product_id or component_id is required', 400)
        product_uuid = self._parse_uuid(product_id, field_name='product_id') if product_id else None
        component_uuid = self._parse_uuid(component_id, field_name='component_id') if component_id else None

        if component_uuid is not None:
            existing = self.db.scalar(select(CustomerPriceOverride).where(
                CustomerPriceOverride.tenant_id == tid,
                CustomerPriceOverride.component_id == component_uuid,
            ))
        else:
            existing = self.db.scalar(select(CustomerPriceOverride).where(
                CustomerPriceOverride.tenant_id == tid,
                CustomerPriceOverride.product_id == product_uuid,
                CustomerPriceOverride.component_id.is_(None),
            ))
        row = existing or CustomerPriceOverride(tenant_id=tid, product_id=product_uuid, component_id=component_uuid)
        row.override_margin_pct = _dec(payload.get('override_margin_pct'))
        row.override_unit_price = _dec(payload.get('override_unit_price'))
        if existing is None:
            self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        audit.log(
            'price_override_created',
            target_tenant_id=str(tid),
            product_id=str(product_uuid) if product_uuid else None,
            component_id=str(component_uuid) if component_uuid else None,
            override_margin_pct=float(row.override_margin_pct) if row.override_margin_pct is not None else None,
            override_unit_price=float(row.override_unit_price) if row.override_unit_price is not None else None,
            updated_existing=existing is not None,
        )
        return row
