"""Square webhook handling + the shared payment-recording path.

``record_completed_payment`` is the single idempotent writer that turns a
captured Square payment into an Invoice (PAID) + Payment (method=SQUARE) row.
Both the synchronous /payment route (CreatePayment returns COMPLETED in sandbox)
and the asynchronous payment.updated webhook funnel through it, so neither path
double-writes (idempotency is keyed on the Square payment id stored in
Payment.external_reference).
"""
import json
import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.lifecycle import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.order import Order
from app.services.square_service import SquareService

logger = logging.getLogger(__name__)


def _record_event(db: Session, event_id: str, event_type: str, payload: dict) -> bool:
    """Insert the event for idempotency. Returns True if it is new.

    Uses CAST(:payload AS jsonb) — text() misparses ``:payload::jsonb`` (binds 'payloa').
    """
    result = db.execute(
        text(
            "INSERT INTO square_events (id, type, payload) "
            "VALUES (:id, :type, CAST(:payload AS jsonb)) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {'id': event_id, 'type': event_type, 'payload': json.dumps(payload)},
    )
    db.commit()
    return result.rowcount > 0


def record_completed_payment(db: Session, payment: dict) -> Payment | None:
    """Idempotently mirror a captured Square payment into Invoice + Payment.

    No-op (returns None) when the payment is not in a paid status, has no
    resolvable order (reference_id), or has already been recorded.
    """
    if not SquareService.is_paid_status(payment.get('status')):
        return None

    payment_id = payment.get('id')
    if not payment_id:
        return None

    # Idempotency: a payment we've already mirrored (route + webhook race, or a
    # webhook replay with a fresh event_id) must not create a second row.
    existing = db.query(Payment).filter(
        Payment.external_reference == payment_id,
        Payment.method == PaymentMethod.SQUARE,
    ).first()
    if existing:
        return existing

    order_ref = payment.get('reference_id')
    if not order_ref:
        logger.warning('Square payment %s has no reference_id; cannot map to an order', payment_id)
        return None
    try:
        order = db.get(Order, uuid.UUID(order_ref))
    except (ValueError, TypeError):
        order = None
    if not order:
        logger.warning('Square payment %s references unknown order %s', payment_id, order_ref)
        return None

    money = payment.get('amount_money') or {}
    amount = (money.get('amount') or 0) / 100
    currency = (money.get('currency') or 'USD').upper()

    invoice = Invoice(
        tenant_id=order.tenant_id,
        billing_month=date.today().replace(day=1),
        amount=amount,
        currency=currency,
        status=InvoiceStatus.PAID,
        due_date=date.today(),
        paid_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.flush()
    record = Payment(
        tenant_id=order.tenant_id,
        invoice_id=invoice.id,
        amount=amount,
        currency=currency,
        method=PaymentMethod.SQUARE,
        status=PaymentStatus.SUCCEEDED,
        external_reference=payment_id,
        # Link the payment back to the order it settled. Payments aren't otherwise
        # tied to an order (only to an invoice), so this is how the order detail
        # knows it's been paid (see orders route _order_paid_at).
        metadata_json={'order_id': str(order.id), 'provider': 'square'},
    )
    db.add(record)
    db.commit()
    return record


def handle_event(db: Session, event: dict) -> None:
    """Dispatch a verified Square webhook event. Idempotent on event_id."""
    event_id = event.get('event_id') or event.get('id')
    event_type = event.get('type', '')
    if not event_id:
        logger.warning('Square webhook missing event_id; skipping')
        return

    if not _record_event(db, event_id, event_type, event):
        logger.info('Square event %s already processed, skipping', event_id)
        return

    handler = _HANDLERS.get(event_type)
    if handler:
        handler(db, event)
    else:
        logger.info('Unhandled Square event type: %s', event_type)


def _extract_payment(event: dict) -> dict:
    # data.object.payment holds the full payment for payment.created/updated.
    return ((event.get('data') or {}).get('object') or {}).get('payment') or {}


def _handle_payment_event(db: Session, event: dict) -> None:
    payment = _extract_payment(event)
    if not payment:
        logger.info('Square %s carried no payment object', event.get('type'))
        return
    record_completed_payment(db, payment)


def _handle_order_event(db: Session, event: dict) -> None:
    # order.updated is a thin summary (no money); we reconcile on the payment
    # event / synchronous CreatePayment instead. Log only.
    obj = ((event.get('data') or {}).get('object') or {}).get('order_updated') or {}
    logger.info('Square order.updated for order=%s (logged only)', obj.get('order_id'))


_HANDLERS = {
    'payment.created': _handle_payment_event,
    'payment.updated': _handle_payment_event,
    'order.updated': _handle_order_event,
}
