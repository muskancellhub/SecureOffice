from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.catalog import CatalogItem
from app.models.pricing import CustomerPricing, DealPricing, ListPrice
from app.models.quote import BillingType, Quote, QuoteStatus
from app.models.user import UserRole

MONEY_QUANT = Decimal('0.01')
PCT_QUANT = Decimal('0.0001')


class PricingService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _to_decimal(value: float | Decimal | int | str, *, fallback: Decimal = Decimal('0')) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:
            return fallback

    @staticmethod
    def _quantize_money(value: Decimal) -> Decimal:
        return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _quantize_pct(value: Decimal) -> Decimal:
        return value.quantize(PCT_QUANT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _is_admin(role: str | None) -> bool:
        return role in {UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value}

    @staticmethod
    def _parse_pct(value: float | Decimal | int | str, *, field_name: str) -> Decimal:
        pct = PricingService._to_decimal(value)
        if pct < Decimal('0') or pct > Decimal('0.95'):
            raise AppError(f'{field_name} must be between 0.0 and 0.95', 422)
        return PricingService._quantize_pct(pct)

    @staticmethod
    def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            raise AppError(f'Invalid {field_name}', 400)

    @staticmethod
    def default_vendor_for_item(item: CatalogItem) -> str:
        if item.vendor:
            return item.vendor
        attrs = item.attributes or {}
        return str(attrs.get('source_vendor') or attrs.get('vendor') or 'CDW')

    @staticmethod
    def calculate_final_unit_price(*, list_price: float | Decimal, default_discount_pct: float | Decimal, incremental_discount_pct: float | Decimal) -> Decimal:
        base = PricingService._to_decimal(list_price)
        default_pct = PricingService._to_decimal(default_discount_pct)
        incremental_pct = PricingService._to_decimal(incremental_discount_pct)
        final_price = base * (Decimal('1') - default_pct) * (Decimal('1') - incremental_pct)
        return PricingService._quantize_money(final_price)

    def get_or_create_customer_pricing(self, tenant_id: str | uuid.UUID) -> CustomerPricing:
        tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else self._parse_uuid(str(tenant_id), field_name='tenant_id')
        row = self.db.get(CustomerPricing, tenant_uuid)
        if row:
            return row

        row = CustomerPricing(tenant_id=tenant_uuid, default_discount_pct=Decimal('0.30'))
        self.db.add(row)
        self.db.flush()
        return row

    def update_customer_discount(self, current_user: dict, default_discount_pct: float) -> CustomerPricing:
        pct = self._parse_pct(default_discount_pct, field_name='default_discount_pct')
        pricing = self.get_or_create_customer_pricing(current_user['tenant_id'])
        pricing.default_discount_pct = pct
        self.db.commit()
        self.db.refresh(pricing)
        return pricing

    def resolve_list_price(self, *, tenant_id: str | uuid.UUID, catalog_item: CatalogItem, vendor: str | None = None) -> ListPrice:
        tenant_uuid = tenant_id if isinstance(tenant_id, uuid.UUID) else self._parse_uuid(str(tenant_id), field_name='tenant_id')
        effective_vendor = (vendor or self.default_vendor_for_item(catalog_item) or 'CDW').strip() or 'CDW'

        stmt = select(ListPrice).where(
            ListPrice.tenant_id == tenant_uuid,
            ListPrice.catalog_item_id == catalog_item.id,
            ListPrice.vendor == effective_vendor,
        )
        row = self.db.scalar(stmt)
        if row:
            return row

        row = ListPrice(
            tenant_id=tenant_uuid,
            catalog_item_id=catalog_item.id,
            vendor=effective_vendor,
            list_price=self._quantize_money(self._to_decimal(catalog_item.price)),
            currency=catalog_item.currency,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def get_or_create_deal_pricing(self, quote: Quote) -> DealPricing:
        row = self.db.get(DealPricing, quote.id)
        if row:
            return row

        row = DealPricing(quote_id=quote.id, incremental_discount_pct=Decimal('0.0'))
        self.db.add(row)
        self.db.flush()
        return row

    def _load_quote_for_tenant(self, tenant_id: str, quote_id: str) -> Quote:
        quote_uuid = self._parse_uuid(quote_id, field_name='quote_id')
        stmt = (
            select(Quote)
            .where(Quote.id == quote_uuid)
            .options(selectinload(Quote.lines), selectinload(Quote.deal_pricing))
        )
        quote = self.db.scalar(stmt)
        if not quote:
            raise NotFoundError('Quote not found')
        if str(quote.tenant_id) != tenant_id:
            raise ForbiddenError('Quote not found in your tenant')
        return quote

    def apply_deal_discount(self, current_user: dict, quote_id: str, incremental_discount_pct: float) -> DealPricing:
        if not self._is_admin(current_user.get('role')):
            raise ForbiddenError('Only admin can update deal pricing')

        pct = self._parse_pct(incremental_discount_pct, field_name='incremental_discount_pct')
        quote = self._load_quote_for_tenant(current_user['tenant_id'], quote_id)
        if quote.status == QuoteStatus.CONVERTED:
            raise AppError('Cannot change pricing for converted quote', 400)

        customer_pricing = self.get_or_create_customer_pricing(current_user['tenant_id'])
        default_pct = self._to_decimal(customer_pricing.default_discount_pct)

        deal_row = self.get_or_create_deal_pricing(quote)
        deal_row.incremental_discount_pct = pct

        one_time_total = Decimal('0')
        monthly_total = Decimal('0')
        for line in quote.lines:
            final_unit = self.calculate_final_unit_price(
                list_price=line.list_price_snapshot,
                default_discount_pct=default_pct,
                incremental_discount_pct=pct,
            )
            line.final_unit_price_snapshot = final_unit
            line_total = final_unit * Decimal(line.qty)
            if line.billing_type == BillingType.RECURRING:
                monthly_total += line_total
            else:
                one_time_total += line_total

        quote.one_time_total = self._quantize_money(one_time_total)
        quote.monthly_total = self._quantize_money(monthly_total)
        quote.projected_12_month_cost = self._quantize_money(one_time_total + (monthly_total * Decimal('12')))

        self.db.commit()
        self.db.refresh(deal_row)
        return deal_row
