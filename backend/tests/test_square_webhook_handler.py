"""Square webhook handler — DB integration with faked Square events (no network)."""
import uuid

import pytest

PFX = 'SQWH-'
EVT_PFX = 'evt_sqwh_'


def _event(type_, payment=None, order_updated=None, event_id=None):
    data_object = {}
    if payment is not None:
        data_object['payment'] = payment
    if order_updated is not None:
        data_object['order_updated'] = order_updated
    return {
        'event_id': event_id or f'{EVT_PFX}{uuid.uuid4().hex}',
        'type': type_,
        'merchant_id': 'MERCHANT_TEST',
        'data': {'type': 'payment', 'object': data_object},
    }


def _payment(payment_id, order_id, status='COMPLETED', amount=25050, currency='USD'):
    return {
        'id': payment_id,
        'status': status,
        'reference_id': str(order_id),
        'amount_money': {'amount': amount, 'currency': currency},
    }


@pytest.fixture(scope='module')
def sqwh_db():
    from sqlalchemy import text
    from app.core.database import engine, SessionLocal, Base
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f'No reachable database: {exc}')

    import app.models  # noqa: F401
    from app.core.runtime_migrations import apply_runtime_migrations
    from app.models.order import Order, OrderStatus
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    tid, uid, order_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.add(Tenant(id=tid, name=f'{PFX}Tenant'))
        db.flush()
        db.add(User(id=uid, email=f'sqwh-{tid}@test.local', name='SQWH Tester',
                    tenant_id=tid, role=UserRole.ADMIN, is_verified=True, password_hash='x'))
        db.flush()
        db.add(Order(id=order_id, tenant_id=tid, created_by_user_id=uid,
                     status=OrderStatus.SUBMITTED))
        db.commit()

    yield SessionLocal, tid, order_id

    with SessionLocal() as db:
        db.execute(text('DELETE FROM payments WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM invoices WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM orders WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM users WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(tid)})
        db.execute(text("DELETE FROM square_events WHERE id LIKE :p"), {'p': f'{EVT_PFX}%'})
        db.commit()


def _handle(db, event):
    from app.services.square_webhook_handler import handle_event
    handle_event(db, event)


def test_idempotency_same_event_handled_once(sqwh_db, monkeypatch):
    import app.services.square_webhook_handler as sqwh
    SessionLocal, tid, order_id = sqwh_db
    calls = []
    monkeypatch.setitem(sqwh._HANDLERS, 'x.test', lambda db, e: calls.append(e['event_id']))
    event = _event('x.test')
    with SessionLocal() as db:
        _handle(db, event)
        _handle(db, event)
    assert calls == [event['event_id']]


def test_unhandled_event_type_is_recorded_noop(sqwh_db):
    SessionLocal, tid, order_id = sqwh_db
    with SessionLocal() as db:
        _handle(db, _event('totally.unknown'))  # must not raise


def test_payment_updated_creates_paid_invoice_and_payment(sqwh_db):
    from app.models.lifecycle import Invoice, InvoiceStatus, Payment, PaymentMethod, PaymentStatus
    SessionLocal, tid, order_id = sqwh_db
    pay_id = f'sqpay_{uuid.uuid4().hex[:16]}'
    with SessionLocal() as db:
        _handle(db, _event('payment.updated', payment=_payment(pay_id, order_id, amount=25050)))
        invoice = (db.query(Invoice).filter(Invoice.tenant_id == tid)
                   .order_by(Invoice.created_at.desc()).first())
        assert invoice.status == InvoiceStatus.PAID
        assert float(invoice.amount) == pytest.approx(250.50)
        assert invoice.currency == 'USD'
        payment = db.query(Payment).filter(Payment.external_reference == pay_id).one()
        assert payment.method == PaymentMethod.SQUARE
        assert payment.status == PaymentStatus.SUCCEEDED


def test_payment_recorded_once_across_replays(sqwh_db):
    """A second event (new event_id) for the same payment id must not double-write."""
    from app.models.lifecycle import Payment
    SessionLocal, tid, order_id = sqwh_db
    pay_id = f'sqpay_{uuid.uuid4().hex[:16]}'
    with SessionLocal() as db:
        _handle(db, _event('payment.created', payment=_payment(pay_id, order_id)))
        _handle(db, _event('payment.updated', payment=_payment(pay_id, order_id)))
        payments = db.query(Payment).filter(Payment.external_reference == pay_id).all()
        assert len(payments) == 1


def test_non_paid_status_is_noop(sqwh_db):
    from app.models.lifecycle import Payment
    SessionLocal, tid, order_id = sqwh_db
    pay_id = f'sqpay_{uuid.uuid4().hex[:16]}'
    with SessionLocal() as db:
        _handle(db, _event('payment.updated',
                           payment=_payment(pay_id, order_id, status='PENDING')))
        assert db.query(Payment).filter(Payment.external_reference == pay_id).count() == 0


def test_unknown_order_reference_is_noop(sqwh_db):
    from app.models.lifecycle import Payment
    SessionLocal, tid, order_id = sqwh_db
    pay_id = f'sqpay_{uuid.uuid4().hex[:16]}'
    with SessionLocal() as db:
        _handle(db, _event('payment.updated',
                           payment=_payment(pay_id, uuid.uuid4())))  # order not in DB
        assert db.query(Payment).filter(Payment.external_reference == pay_id).count() == 0


def test_order_updated_logs_only(sqwh_db):
    from app.models.lifecycle import Payment
    SessionLocal, tid, order_id = sqwh_db
    with SessionLocal() as db:
        before = db.query(Payment).filter(Payment.tenant_id == tid).count()
        _handle(db, _event('order.updated', order_updated={'order_id': 'sqord_1'}))
        assert db.query(Payment).filter(Payment.tenant_id == tid).count() == before


def test_record_completed_payment_direct_is_idempotent(sqwh_db):
    """The synchronous route path and webhook share record_completed_payment."""
    from app.services.square_webhook_handler import record_completed_payment
    from app.models.lifecycle import Payment
    SessionLocal, tid, order_id = sqwh_db
    pay_id = f'sqpay_{uuid.uuid4().hex[:16]}'
    payment = _payment(pay_id, order_id)
    with SessionLocal() as db:
        first = record_completed_payment(db, payment)
        second = record_completed_payment(db, payment)
        assert first is not None
        assert second.id == first.id
        assert db.query(Payment).filter(Payment.external_reference == pay_id).count() == 1
