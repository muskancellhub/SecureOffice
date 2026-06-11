"""Stripe webhook handler — DB integration with faked stripe events (no network)."""
import json
import uuid
from datetime import date

import pytest

PFX = 'SWHSVC-'
EVT_PFX = 'evt_swhsvc_'


class FakeEventData:
    """event.data must stringify to JSON: _record_event does str(event.data)::jsonb."""

    def __init__(self, obj):
        self.object = obj

    def __str__(self):
        return json.dumps({'object': self.object})


class FakeEvent:
    def __init__(self, type_, obj):
        self.id = f'{EVT_PFX}{uuid.uuid4().hex}'
        self.type = type_
        self.data = FakeEventData(obj)


class FakeStripeObj(dict):
    """Stripe SDK objects allow both dict and attribute access."""
    __getattr__ = dict.__getitem__


@pytest.fixture(scope='module')
def swh_db():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.models.lifecycle import Contract, Subscription, SubscriptionStatus
    from app.models.order import Order, OrderStatus
    from app.models.quote import BillingInterval
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    tid, uid = uuid.uuid4(), uuid.uuid4()
    order_id = uuid.uuid4()
    stripe_sub_id = f'sub_{uuid.uuid4().hex[:16]}'
    with SessionLocal() as db:
        db.add(Tenant(id=tid, name=f'{PFX}Tenant'))
        db.flush()
        db.add(User(id=uid, email=f'swhsvc-{tid}@test.local', name='SWH Tester',
                    tenant_id=tid, role=UserRole.ADMIN, is_verified=True, password_hash='x'))
        db.flush()
        order = Order(id=order_id, tenant_id=tid, created_by_user_id=uid,
                      status=OrderStatus.SUBMITTED)
        db.add(order)
        db.flush()
        contract = Contract(tenant_id=tid, order_id=order_id, created_by=uid)
        db.add(contract)
        db.flush()
        db.add(Subscription(tenant_id=tid, contract_id=contract.id, name=f'{PFX}Sub',
                            unit_price=49.0, qty=1, interval=BillingInterval.MONTH,
                            status=SubscriptionStatus.PAUSED,
                            stripe_subscription_id=stripe_sub_id))
        db.commit()

    yield SessionLocal, tid, order_id, stripe_sub_id

    with SessionLocal() as db:
        db.execute(text('DELETE FROM payments WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM invoices WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM subscriptions WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM contracts WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM orders WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM users WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(tid)})
        db.execute(text("DELETE FROM stripe_events WHERE id LIKE :p"), {'p': f'{EVT_PFX}%'})
        db.commit()


def _handle(db, event):
    from app.services.stripe_webhook_handler import handle_event
    handle_event(db, event)


def test_idempotency_same_event_handled_once(swh_db, monkeypatch):
    import app.services.stripe_webhook_handler as swh
    SessionLocal, tid, order_id, sub_id = swh_db
    calls = []
    monkeypatch.setitem(swh._HANDLERS, 'x.test', lambda db, e: calls.append(e.id))
    event = FakeEvent('x.test', {'id': 'obj_1'})
    with SessionLocal() as db:
        _handle(db, event)
        _handle(db, event)
    assert calls == [event.id]


def test_unhandled_event_type_is_recorded_noop(swh_db):
    SessionLocal, tid, order_id, sub_id = swh_db
    with SessionLocal() as db:
        _handle(db, FakeEvent('totally.unknown', {'id': 'obj_x'}))  # must not raise


def test_checkout_subscription_activates_existing_local_sub(swh_db, monkeypatch):
    import stripe
    from app.models.lifecycle import Subscription, SubscriptionStatus
    SessionLocal, tid, order_id, sub_id = swh_db
    fake_sub = FakeStripeObj(id=sub_id, items={'data': [{'price': {'id': 'price_x'}}]})
    monkeypatch.setattr(stripe.Subscription, 'retrieve', staticmethod(lambda s: fake_sub))
    event = FakeEvent('checkout.session.completed', {
        'mode': 'subscription', 'client_reference_id': str(tid), 'subscription': sub_id,
    })
    with SessionLocal() as db:
        _handle(db, event)
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == sub_id).one()
        assert sub.status == SubscriptionStatus.ACTIVE


def test_checkout_subscription_creates_missing_local_sub(swh_db, monkeypatch):
    import stripe
    from app.models.lifecycle import Subscription, SubscriptionStatus
    SessionLocal, tid, order_id, sub_id = swh_db
    new_sub_id = f'sub_{uuid.uuid4().hex[:16]}'
    fake_sub = FakeStripeObj(id=new_sub_id, items={'data': [{'price': {'id': 'price_y'}}]})
    monkeypatch.setattr(stripe.Subscription, 'retrieve', staticmethod(lambda s: fake_sub))
    event = FakeEvent('checkout.session.completed', {
        'mode': 'subscription', 'client_reference_id': str(tid), 'subscription': new_sub_id,
    })
    with SessionLocal() as db:
        _handle(db, event)
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == new_sub_id).one()
        # tenant-level checkout subscription: no local order/contract behind it
        assert sub.contract_id is None
        assert sub.tenant_id == tid
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.stripe_price_id == 'price_y'


def test_checkout_payment_creates_paid_invoice_and_payment(swh_db):
    from app.models.lifecycle import Invoice, InvoiceStatus, Payment, PaymentStatus
    SessionLocal, tid, order_id, sub_id = swh_db
    event = FakeEvent('checkout.session.completed', {
        'mode': 'payment', 'client_reference_id': str(tid),
        'metadata': {'order_id': str(order_id)},
        'amount_total': 25050, 'currency': 'usd', 'payment_intent': 'pi_test_1',
    })
    with SessionLocal() as db:
        _handle(db, event)
        invoice = (db.query(Invoice).filter(Invoice.tenant_id == tid)
                   .order_by(Invoice.created_at.desc()).first())
        assert invoice.status == InvoiceStatus.PAID
        assert float(invoice.amount) == pytest.approx(250.50)
        assert invoice.currency == 'USD'
        payment = db.query(Payment).filter(Payment.invoice_id == invoice.id).one()
        assert payment.status == PaymentStatus.SUCCEEDED
        assert payment.external_reference == 'pi_test_1'


def test_checkout_payment_without_order_id_is_noop(swh_db):
    from app.models.lifecycle import Invoice
    SessionLocal, tid, order_id, sub_id = swh_db
    with SessionLocal() as db:
        before = db.query(Invoice).filter(Invoice.tenant_id == tid).count()
        _handle(db, FakeEvent('checkout.session.completed', {
            'mode': 'payment', 'client_reference_id': str(tid), 'metadata': {},
        }))
        assert db.query(Invoice).filter(Invoice.tenant_id == tid).count() == before


def test_invoice_paid_autocreates_from_subscription_and_is_replay_safe(swh_db):
    from app.models.lifecycle import Invoice, InvoiceStatus, Payment
    SessionLocal, tid, order_id, sub_id = swh_db
    stripe_inv = f'in_{uuid.uuid4().hex[:16]}'
    payload = {'id': stripe_inv, 'subscription': sub_id, 'amount_paid': 4900,
               'currency': 'usd', 'payment_intent': 'pi_inv_1'}
    with SessionLocal() as db:
        _handle(db, FakeEvent('invoice.paid', payload))
        invoice = db.query(Invoice).filter(Invoice.stripe_invoice_id == stripe_inv).one()
        assert invoice.status == InvoiceStatus.PAID
        assert float(invoice.amount) == 49.0
        # replay with a NEW event id but the same payment_intent → no duplicate payment
        _handle(db, FakeEvent('invoice.paid', payload))
        payments = db.query(Payment).filter(Payment.invoice_id == invoice.id).all()
        assert len(payments) == 1


def test_invoice_paid_without_matching_subscription_is_noop(swh_db):
    from app.models.lifecycle import Invoice
    SessionLocal, tid, order_id, sub_id = swh_db
    with SessionLocal() as db:
        before = db.query(Invoice).count()
        _handle(db, FakeEvent('invoice.paid', {
            'id': f'in_{uuid.uuid4().hex[:12]}', 'subscription': 'sub_unknown',
            'amount_paid': 100, 'currency': 'usd', 'payment_intent': 'pi_x',
        }))
        assert db.query(Invoice).count() == before


def test_invoice_payment_failed_marks_due_and_records_failed_payment(swh_db):
    from app.models.lifecycle import Invoice, InvoiceStatus, Payment, PaymentStatus
    SessionLocal, tid, order_id, sub_id = swh_db
    stripe_inv = f'in_{uuid.uuid4().hex[:16]}'
    with SessionLocal() as db:
        # seed a local invoice directly (a second autocreate for the same
        # subscription+month would trip uq_invoices_subscription_billing_month)
        db.add(Invoice(tenant_id=tid, billing_month=date(2026, 1, 1), amount=49.0,
                       currency='USD', status=InvoiceStatus.PAID,
                       due_date=date(2026, 1, 15), stripe_invoice_id=stripe_inv))
        db.commit()
        _handle(db, FakeEvent('invoice.payment_failed', {
            'id': stripe_inv, 'amount_due': 4900, 'currency': 'usd',
            'payment_intent': 'pi_inv_3',
        }))
        invoice = db.query(Invoice).filter(Invoice.stripe_invoice_id == stripe_inv).one()
        assert invoice.status == InvoiceStatus.DUE
        failed = (db.query(Payment)
                  .filter(Payment.invoice_id == invoice.id,
                          Payment.status == PaymentStatus.FAILED).one())
        assert failed.external_reference == 'pi_inv_3'


def test_invoice_payment_failed_unknown_invoice_is_noop(swh_db):
    SessionLocal, tid, order_id, sub_id = swh_db
    with SessionLocal() as db:
        _handle(db, FakeEvent('invoice.payment_failed', {
            'id': 'in_unknown', 'amount_due': 1, 'currency': 'usd',
        }))  # must not raise


def test_subscription_updated_status_and_cancel_at(swh_db):
    from datetime import datetime, timezone
    from app.models.lifecycle import Subscription, SubscriptionStatus
    SessionLocal, tid, order_id, sub_id = swh_db
    cancel_ts = int(datetime(2026, 12, 31, tzinfo=timezone.utc).timestamp())
    with SessionLocal() as db:
        _handle(db, FakeEvent('customer.subscription.updated', {
            'id': sub_id, 'status': 'canceled', 'cancel_at': cancel_ts,
        }))
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == sub_id).one()
        assert sub.status == SubscriptionStatus.CANCELLED
        assert sub.end_date == date(2026, 12, 31)
        # unknown stripe status leaves local status unchanged
        _handle(db, FakeEvent('customer.subscription.updated', {
            'id': sub_id, 'status': 'something_new',
        }))
        db.refresh(sub)
        assert sub.status == SubscriptionStatus.CANCELLED
        # unknown subscription → warning no-op
        _handle(db, FakeEvent('customer.subscription.updated', {
            'id': 'sub_missing', 'status': 'active',
        }))


def test_subscription_deleted_cancels_and_sets_end_date(swh_db):
    from datetime import datetime, timezone
    from app.models.lifecycle import Subscription, SubscriptionStatus
    SessionLocal, tid, order_id, sub_id = swh_db
    ended_ts = int(datetime(2027, 1, 15, tzinfo=timezone.utc).timestamp())
    with SessionLocal() as db:
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == sub_id).one()
        sub.status = SubscriptionStatus.ACTIVE
        db.commit()
        _handle(db, FakeEvent('customer.subscription.deleted', {
            'id': sub_id, 'ended_at': ended_ts,
        }))
        db.refresh(sub)
        assert sub.status == SubscriptionStatus.CANCELLED
        assert sub.end_date == date(2027, 1, 15)


def test_payment_intent_events_log_only(swh_db):
    SessionLocal, tid, order_id, sub_id = swh_db
    with SessionLocal() as db:
        _handle(db, FakeEvent('payment_intent.succeeded', {'id': 'pi_log_1'}))
        _handle(db, FakeEvent('payment_intent.payment_failed', {'id': 'pi_log_2'}))
