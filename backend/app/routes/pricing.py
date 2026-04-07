from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.permissions import PERM_MANAGE_PRICING
from app.middleware.dependencies import get_current_user
from app.schemas.pricing import (
    CustomerPricingResponse,
    DealPricingResponse,
    UpdateCustomerPricingRequest,
    UpdateDealPricingRequest,
)
from app.services.authorization_service import AuthorizationService
from app.services.pricing_service import PricingService

router = APIRouter(prefix='/pricing', tags=['Pricing'])


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
