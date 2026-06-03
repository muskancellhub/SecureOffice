import logging
import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.middleware.dependencies import get_current_user
from app.models.order import Order
from app.services.stripe_service import StripeService
from app.services import stripe_webhook_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/billing/stripe', tags=['Stripe'])


class SubscriptionCheckoutRequest(BaseModel):
    price_id: str


class CheckoutUrlResponse(BaseModel):
    url: str


class CheckoutSessionResponse(BaseModel):
    status: str | None
    payment_status: str | None
    customer_email: str | None


@router.post('/checkout/subscription', response_model=CheckoutUrlResponse)
def create_subscription_checkout(
    payload: SubscriptionCheckoutRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.tenant import Tenant
    tenant = db.get(Tenant, uuid.UUID(str(current_user['tenant_id'])))
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found')
    svc = StripeService(db)
    url = svc.create_subscription_checkout(tenant, payload.price_id)
    return CheckoutUrlResponse(url=url)


@router.post('/checkout/order/{order_id}', response_model=CheckoutUrlResponse)
def create_order_checkout(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.tenant import Tenant
    order = db.get(Order, uuid.UUID(order_id))
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order not found')
    user_tenant_id = uuid.UUID(str(current_user['tenant_id']))
    if order.tenant_id != user_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Not authorized for this order')
    tenant = db.get(Tenant, order.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found')
    svc = StripeService(db)
    url = svc.create_order_checkout(tenant, order)
    return CheckoutUrlResponse(url=url)


@router.get('/session/{session_id}', response_model=CheckoutSessionResponse)
def get_checkout_session(session_id: str):
    data = StripeService.retrieve_session(session_id)
    return CheckoutSessionResponse(**data)


@router.post('/webhook')
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature', '')
    try:
        event = StripeService.verify_webhook(payload, sig_header)
    except (stripe.SignatureVerificationError, ValueError) as exc:
        logger.warning('Stripe webhook signature verification failed: %s', exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid signature')
    stripe_webhook_handler.handle_event(db, event)
    return {'received': True}
