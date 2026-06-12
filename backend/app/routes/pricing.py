from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_PRICING
from app.middleware.dependencies import get_current_user
from app.middleware.tenant_context import TenantContext, assert_tenant_access, get_tenant_context
from app.schemas.pricing import (
    ComponentPreviewRequest,
    CustomerPricingResponse,
    DealPricingResponse,
    StandaloneComponentPreviewRequest,
    UpdateCustomerPricingRequest,
    UpdateDealPricingRequest,
)
from app.schemas.products import (
    CommercialResponse,
    CreateFinancingTermsRequest,
    FinancingTermsResponse,
    PriceOverrideRequest,
    PriceOverrideResponse,
    UpdateCommercialRequest,
)
from app.services.authorization_service import AuthorizationService
from app.services.component_pricing_service import ComponentPricingService
from app.services.pricing_service import PricingService
from app.services.product_admin_service import ProductAdminService

router = APIRouter(prefix='/pricing', tags=['Pricing'])


def _serialize_financing(t) -> FinancingTermsResponse:
    return FinancingTermsResponse(
        id=str(t.id), name=t.name, term_months=t.term_months,
        annual_rate_pct=float(t.annual_rate_pct), subscription_interval=t.subscription_interval,
        is_default=t.is_default, is_active=t.is_active,
    )


@router.get('/financing-terms', response_model=list[FinancingTermsResponse])
def list_financing_terms(
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRICING)
    return [_serialize_financing(t) for t in ProductAdminService(db).list_financing_terms(ctx.effective_tenant_id)]


@router.post('/financing-terms', response_model=FinancingTermsResponse)
def create_financing_terms(
    payload: CreateFinancingTermsRequest,
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRICING)
    return _serialize_financing(
        ProductAdminService(db).create_financing_terms(ctx.effective_tenant_id, payload.model_dump(exclude_unset=True))
    )


@router.patch('/customers/{tenant_id}/commercial', response_model=CommercialResponse)
def update_customer_commercial(
    tenant_id: str,
    payload: UpdateCommercialRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRICING)
    assert_tenant_access(current_user, tenant_id)
    p = ProductAdminService(db).update_customer_commercial(tenant_id, payload.model_dump(exclude_unset=True))
    return CommercialResponse(
        tenant_id=str(p.tenant_id), default_discount_pct=float(p.default_discount_pct),
        default_margin_pct=float(p.default_margin_pct) if p.default_margin_pct is not None else None,
        opex_eligible=p.opex_eligible,
        credit_status=p.credit_status, credit_limit=float(p.credit_limit) if p.credit_limit is not None else None,
        updated_at=p.updated_at,
    )


@router.post('/customers/{tenant_id}/price-overrides', response_model=PriceOverrideResponse)
def upsert_price_override(
    tenant_id: str,
    payload: PriceOverrideRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRICING)
    assert_tenant_access(current_user, tenant_id)
    o = ProductAdminService(db).upsert_price_override(tenant_id, payload.model_dump(exclude_unset=True))
    return PriceOverrideResponse(
        id=str(o.id), tenant_id=str(o.tenant_id),
        product_id=str(o.product_id) if o.product_id else None,
        component_id=str(o.component_id) if o.component_id else None,
        override_margin_pct=float(o.override_margin_pct) if o.override_margin_pct is not None else None,
        override_unit_price=float(o.override_unit_price) if o.override_unit_price is not None else None,
    )


@router.post('/component-preview')
def component_preview(
    payload: ComponentPreviewRequest,
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Compute the CAPEX/OPEX price tree for a product (Phase 2). No persistence.

    Lives at /pricing/component-preview rather than /quotes/preview because the
    latter already serves the network-design BOM preview. Decimal values are
    JSON-encoded as numbers by FastAPI's jsonable_encoder. Priced for the
    EFFECTIVE tenant (X-Tenant-Id for SUPER_ADMIN) so the admin grid and the
    tenant switcher reprice live (Phase 7).
    """
    return ComponentPricingService(db).price_product(
        payload.product_id,
        financial_model=payload.financial_model,
        interval=payload.interval,
        selections=payload.selections,
        tenant_id=ctx.effective_tenant_id,
    )


@router.post('/component-preview/standalone')
def standalone_component_preview(
    payload: StandaloneComponentPreviewRequest,
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Price a single component à-la-carte (Phase 7 D10) — one extra voice
    line, a SIM, a router-only accessory — without re-pricing the whole
    product tree."""
    return ComponentPricingService(db).price_standalone_component(
        payload.component_id,
        qty=payload.qty,
        financial_model=payload.financial_model,
        interval=payload.interval,
        tenant_id=ctx.effective_tenant_id,
    )


@router.get('/customer', response_model=CustomerPricingResponse)
def get_customer_pricing(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRICING)
    pricing = PricingService(db).get_or_create_customer_pricing(current_user['tenant_id'])
    db.commit()
    db.refresh(pricing)
    return CustomerPricingResponse(
        tenant_id=str(pricing.tenant_id),
        default_discount_pct=float(pricing.default_discount_pct),
        updated_at=pricing.updated_at,
    )


@router.put('/customer', response_model=CustomerPricingResponse)
def update_customer_pricing(
    payload: UpdateCustomerPricingRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthorizationService(db).require(current_user, PERM_MANAGE_PRICING)
    pricing = PricingService(db).update_customer_discount(current_user, payload.default_discount_pct)
    return CustomerPricingResponse(
        tenant_id=str(pricing.tenant_id),
        default_discount_pct=float(pricing.default_discount_pct),
        updated_at=pricing.updated_at,
    )


@router.put('/deal/{quote_id}', response_model=DealPricingResponse)
def update_deal_pricing(
    quote_id: str,
    payload: UpdateDealPricingRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deal = PricingService(db).apply_deal_discount(current_user, quote_id, payload.incremental_discount_pct)
    return DealPricingResponse(
        quote_id=str(deal.quote_id),
        incremental_discount_pct=float(deal.incremental_discount_pct),
        updated_at=deal.updated_at,
    )
