"""Square payment routes under /billing/square (docs/SQUARE_MIGRATION_PLAN.md §6.3).

Enforces auth + tenant/order ownership checks, and charges an embedded-widget
card nonce server-side (no hosted-page redirect).
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.middleware.dependencies import get_current_user
from app.models.order import Order
from app.services import square_webhook_handler
from app.services.audit_logger import audit
from app.services.square_service import SquareError, SquareService

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/billing/square', tags=['Square'])

_settings = get_settings()


class SquarePaymentRequest(BaseModel):
    order_id: str
    source_id: str
    idempotency_key: str | None = None


class SquarePaymentResponse(BaseModel):
    payment_id: str | None
    status: str | None
    amount: float | None
    currency: str | None


def _to_response(payment: dict) -> SquarePaymentResponse:
    money = payment.get('amount_money') or {}
    amount = money.get('amount')
    return SquarePaymentResponse(
        payment_id=payment.get('id'),
        status=payment.get('status'),
        amount=(amount / 100) if amount is not None else None,
        currency=money.get('currency'),
    )


@router.post('/payment', response_model=SquarePaymentResponse)
def create_payment(
    payload: SquarePaymentRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        order_uuid = uuid.UUID(payload.order_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid order id')

    order = db.get(Order, order_uuid)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Order not found')
    user_tenant_id = uuid.UUID(str(current_user['tenant_id']))
    if order.tenant_id != user_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Not authorized for this order')

    svc = SquareService(db)
    idempotency_key = payload.idempotency_key or str(uuid.uuid4())
    try:
        payment = svc.create_payment(order, payload.source_id, idempotency_key)
    except SquareError as exc:
        logger.warning('Square CreatePayment failed for order %s: %s', order.id, exc)
        audit.log('square_payment_created', status='failure', level=logging.WARNING,
                  order_id=str(order.id), reason=str(exc))
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc))

    # Sandbox CreatePayment returns COMPLETED synchronously — record immediately
    # so Billing history reflects it without waiting on the webhook. The webhook
    # path is idempotent on the same payment id, so this never double-writes.
    if SquareService.is_paid_status(payment.get('status')):
        square_webhook_handler.record_completed_payment(db, payment)

    return _to_response(payment)


@router.get('/payment/{payment_id}', response_model=SquarePaymentResponse)
def get_payment(
    payment_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        payment = SquareService(db).get_payment(payment_id)
    except SquareError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return _to_response(payment)


@router.post('/webhook')
async def square_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get('x-square-hmacsha256-signature', '')
    notification_url = _settings.square_webhook_notification_url or str(request.url)

    if not SquareService.verify_webhook(body, signature, notification_url):
        logger.warning('Square webhook signature verification failed')
        audit.log('square_webhook_received', status='failure', level=logging.WARNING,
                  actor='system', reason='invalid_signature')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid signature')

    try:
        event = await request.json()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid JSON')

    square_webhook_handler.handle_event(db, event)
    audit.log('square_webhook_received', actor='system',
              event_type=event.get('type'), event_id=event.get('event_id'))
    return {'received': True}
