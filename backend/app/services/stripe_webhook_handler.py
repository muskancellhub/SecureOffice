import logging
import uuid
from datetime import date, datetime, timezone

import stripe
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.lifecycle import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)
from app.models.order import Order

logger = logging.getLogger(__name__)


def _record_event(db: Session, event: stripe.Event) -> bool:
    """Insert event for idempotency. Returns True if this is a new event."""
    result = db.execute(
        text(
            "INSERT INTO stripe_events (id, type, payload) "
            "VALUES (:id, :type, :payload::jsonb) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {'id': event.id, 'type': event.type, 'payload': str(event.data)},
    )
    db.commit()
    return result.rowcount > 0


def handle_event(db: Session, event: stripe.Event) -> None:
    if not _record_event(db, event):
        logger.info('Stripe event %s already processed, skipping', event.id)
        return

    handler = _HANDLERS.get(event.type)
    if handler:
        handler(db, event)
    else:
        logger.info('Unhandled Stripe event type: %s', event.type)


def _handle_checkout_session_completed(db: Session, event: stripe.Event) -> None:
    session = event.data.object
    mode = session.get('mode')
    tenant_id = session.get('client_reference_id')

    if mode == 'subscription':
        stripe_sub = stripe.Subscription.retrieve(session['subscription'])
        sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == stripe_sub.id,
        ).first()
        if not sub:
            price_id = stripe_sub['items']['data'][0]['price']['id'] if stripe_sub.get('items', {}).get('data') else None
            sub = Subscription(
                tenant_id=uuid.UUID(tenant_id),
                contract_id=None,
                name='Stripe Subscription',
                unit_price=0,
                stripe_subscription_id=stripe_sub.id,
                stripe_price_id=price_id,
                status=SubscriptionStatus.ACTIVE,
            )
            db.add(sub)
            db.commit()
        else:
            sub.status = SubscriptionStatus.ACTIVE
            db.commit()

    elif mode == 'payment':
        metadata = session.get('metadata', {})
        order_id = metadata.get('order_id')
        if order_id:
            order = db.get(Order, uuid.UUID(order_id))
            if order:
                invoice = Invoice(
                    tenant_id=order.tenant_id,
                    billing_month=date.today().replace(day=1),
                    amount=session.get('amount_total', 0) / 100,
                    currency=(session.get('currency') or 'usd').upper(),
                    status=InvoiceStatus.PAID,
                    due_date=date.today(),
                    paid_at=datetime.now(timezone.utc),
                )
                db.add(invoice)
                db.flush()
                payment = Payment(
                    tenant_id=order.tenant_id,
                    invoice_id=invoice.id,
                    amount=invoice.amount,
                    currency=invoice.currency,
                    method=PaymentMethod.STRIPE,
                    status=PaymentStatus.SUCCEEDED,
                    external_reference=session.get('payment_intent'),
                )
                db.add(payment)
                db.commit()


def _handle_invoice_paid(db: Session, event: stripe.Event) -> None:
    inv_obj = event.data.object
    stripe_invoice_id = inv_obj.get('id')

    invoice = db.query(Invoice).filter(Invoice.stripe_invoice_id == stripe_invoice_id).first()
    if not invoice:
        tenant_sub = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == inv_obj.get('subscription'),
        ).first()
        if tenant_sub:
            invoice = Invoice(
                tenant_id=tenant_sub.tenant_id,
                subscription_id=tenant_sub.id,
                billing_month=date.today().replace(day=1),
                amount=inv_obj.get('amount_paid', 0) / 100,
                currency=(inv_obj.get('currency') or 'usd').upper(),
                status=InvoiceStatus.PAID,
                due_date=date.today(),
                paid_at=datetime.now(timezone.utc),
                stripe_invoice_id=stripe_invoice_id,
            )
            db.add(invoice)
            db.flush()
        else:
            logger.warning('invoice.paid: no matching subscription for %s', stripe_invoice_id)
            return

    if invoice.status != InvoiceStatus.PAID:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.now(timezone.utc)

    existing_payment = db.query(Payment).filter(
        Payment.invoice_id == invoice.id,
        Payment.external_reference == inv_obj.get('payment_intent'),
    ).first()
    if not existing_payment:
        payment = Payment(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            amount=inv_obj.get('amount_paid', 0) / 100,
            currency=(inv_obj.get('currency') or 'usd').upper(),
            method=PaymentMethod.STRIPE,
            status=PaymentStatus.SUCCEEDED,
            external_reference=inv_obj.get('payment_intent'),
        )
        db.add(payment)
    db.commit()


def _handle_invoice_payment_failed(db: Session, event: stripe.Event) -> None:
    inv_obj = event.data.object
    stripe_invoice_id = inv_obj.get('id')

    invoice = db.query(Invoice).filter(Invoice.stripe_invoice_id == stripe_invoice_id).first()
    if invoice:
        invoice.status = InvoiceStatus.DUE
        payment = Payment(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            amount=inv_obj.get('amount_due', 0) / 100,
            currency=(inv_obj.get('currency') or 'usd').upper(),
            method=PaymentMethod.STRIPE,
            status=PaymentStatus.FAILED,
            external_reference=inv_obj.get('payment_intent'),
        )
        db.add(payment)
        db.commit()
    else:
        logger.warning('invoice.payment_failed: no local invoice for %s', stripe_invoice_id)


def _handle_subscription_updated(db: Session, event: stripe.Event) -> None:
    sub_obj = event.data.object
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == sub_obj.get('id'),
    ).first()
    if not sub:
        logger.warning('subscription.updated: no local subscription for %s', sub_obj.get('id'))
        return
    stripe_status = sub_obj.get('status', '')
    status_map = {
        'active': SubscriptionStatus.ACTIVE,
        'paused': SubscriptionStatus.PAUSED,
        'canceled': SubscriptionStatus.CANCELLED,
        'cancelled': SubscriptionStatus.CANCELLED,
        'unpaid': SubscriptionStatus.PAUSED,
        'past_due': SubscriptionStatus.ACTIVE,
    }
    if stripe_status in status_map:
        sub.status = status_map[stripe_status]
    cancel_at = sub_obj.get('cancel_at')
    if cancel_at:
        sub.end_date = datetime.fromtimestamp(cancel_at, tz=timezone.utc).date()
    db.commit()


def _handle_subscription_deleted(db: Session, event: stripe.Event) -> None:
    sub_obj = event.data.object
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == sub_obj.get('id'),
    ).first()
    if sub:
        sub.status = SubscriptionStatus.CANCELLED
        ended_at = sub_obj.get('ended_at')
        if ended_at:
            sub.end_date = datetime.fromtimestamp(ended_at, tz=timezone.utc).date()
        db.commit()


def _handle_payment_intent_event(db: Session, event: stripe.Event) -> None:
    logger.info('Stripe %s for pi=%s (logged only)', event.type, event.data.object.get('id'))


_HANDLERS = {
    'checkout.session.completed': _handle_checkout_session_completed,
    'invoice.paid': _handle_invoice_paid,
    'invoice.payment_failed': _handle_invoice_payment_failed,
    'customer.subscription.updated': _handle_subscription_updated,
    'customer.subscription.deleted': _handle_subscription_deleted,
    'payment_intent.succeeded': _handle_payment_intent_event,
    'payment_intent.payment_failed': _handle_payment_intent_event,
}
