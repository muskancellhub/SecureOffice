"""BillingService — pure date/charge helpers + DB integration (skips without Postgres)."""
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.billing_service import BillingService

PFX = 'BILLSVC-'


# ---------- pure helpers (no DB) ----------

def test_add_months_rollover_and_negative():
    assert BillingService._add_months(date(2026, 11, 15), 3) == date(2027, 2, 1)
    assert BillingService._add_months(date(2026, 1, 15), -2) == date(2025, 11, 1)


def test_month_key_zero_pads():
    assert BillingService._month_key(date(2026, 3, 1)) == '2026-03'


def _sub(*, status='ACTIVE', interval='MONTH', start=date(2026, 1, 1), end=None,
         unit_price=10.0, qty=2):
    from app.models.lifecycle import SubscriptionStatus
    from app.models.quote import BillingInterval
    return SimpleNamespace(
        status=SubscriptionStatus(status), interval=BillingInterval(interval),
        start_date=start, end_date=end, unit_price=unit_price, qty=qty,
    )


def test_is_active_for_month_window():
    month = date(2026, 6, 1)
    assert BillingService._is_active_for_month(_sub(), month) is True
    assert BillingService._is_active_for_month(_sub(start=date(2026, 7, 1)), month) is False
    assert BillingService._is_active_for_month(_sub(end=date(2026, 5, 31)), month) is False
    assert BillingService._is_active_for_month(_sub(status='CANCELLED'), month) is False


def test_recurring_charge_month_vs_year():
    month = date(2026, 6, 1)
    assert BillingService._recurring_charge_for_month(_sub(unit_price=10, qty=3), month) == 30.0
    yearly = _sub(interval='YEAR', start=date(2025, 6, 10), unit_price=120, qty=1)
    assert BillingService._recurring_charge_for_month(yearly, month) == 120.0
    off_month = _sub(interval='YEAR', start=date(2025, 3, 10), unit_price=120, qty=1)
    assert BillingService._recurring_charge_for_month(off_month, month) == 0.0


def test_parse_uuid_invalid_raises_not_found():
    from app.core.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        BillingService._parse_uuid('nope', field_name='invoice_id')


# ---------- DB integration ----------

@pytest.fixture(scope='module')
def bill_db():
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
    from app.models.order import Order, OrderLine, OrderStatus
    from app.models.quote import BillingInterval, BillingType, QuoteLineType
    from app.models.tenant import Tenant
    from app.models.user import User, UserRole
    apply_runtime_migrations()
    Base.metadata.create_all(bind=engine)

    tid = uuid.uuid4()
    admin_id, user_id = uuid.uuid4(), uuid.uuid4()
    current_month = date.today().replace(day=1)
    with SessionLocal() as db:
        db.add(Tenant(id=tid, name=f'{PFX}Tenant'))
        db.flush()
        db.add(User(id=admin_id, email=f'billsvc-admin-{tid}@test.local', name='Bill Admin',
                    tenant_id=tid, role=UserRole.ADMIN, is_verified=True, password_hash='x'))
        db.add(User(id=user_id, email=f'billsvc-user-{tid}@test.local', name='Bill User',
                    tenant_id=tid, role=UserRole.USER, is_verified=True, password_hash='x'))
        db.flush()  # users must exist before FK-dependent orders/contracts
        order = Order(tenant_id=tid, created_by_user_id=admin_id, status=OrderStatus.SUBMITTED)
        db.add(order)
        db.flush()
        db.add(OrderLine(order_id=order.id, line_type=QuoteLineType.DEVICE,
                         name_snapshot=f'{PFX}Router', qty=2,
                         final_unit_price_snapshot=100.0, billing_type=BillingType.ONE_TIME))
        contract = Contract(tenant_id=tid, order_id=order.id, created_by=admin_id)
        db.add(contract)
        db.flush()
        db.add(Subscription(tenant_id=tid, contract_id=contract.id, name=f'{PFX}Monthly',
                            unit_price=25.0, qty=2, interval=BillingInterval.MONTH,
                            status=SubscriptionStatus.ACTIVE, start_date=current_month))
        db.add(Subscription(tenant_id=tid, contract_id=contract.id, name=f'{PFX}Yearly',
                            unit_price=600.0, qty=1, interval=BillingInterval.YEAR,
                            status=SubscriptionStatus.ACTIVE, start_date=current_month))
        db.add(Subscription(tenant_id=tid, contract_id=contract.id, name=f'{PFX}Dead',
                            unit_price=999.0, qty=1, interval=BillingInterval.MONTH,
                            status=SubscriptionStatus.CANCELLED, start_date=current_month))
        db.commit()

    admin = {'user_id': str(admin_id), 'tenant_id': str(tid), 'role': UserRole.ADMIN.value}
    plain = {'user_id': str(user_id), 'tenant_id': str(tid), 'role': UserRole.USER.value}
    yield SessionLocal, admin, plain, tid

    with SessionLocal() as db:
        db.execute(text('DELETE FROM payments WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM invoices WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM subscriptions WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM contracts WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM order_lines WHERE order_id IN (SELECT id FROM orders WHERE tenant_id = :t)'), {'t': str(tid)})
        db.execute(text('DELETE FROM orders WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM users WHERE tenant_id = :t'), {'t': str(tid)})
        db.execute(text('DELETE FROM tenants WHERE id = :t'), {'t': str(tid)})
        db.commit()


def _svc(db):
    return BillingService(db)


def test_overview_admin_buckets(bill_db):
    SessionLocal, admin, plain, tid = bill_db
    with SessionLocal() as db:
        overview = _svc(db).get_billing_overview(admin)
        current_key = BillingService._month_key(date.today().replace(day=1))
        current = next(m for m in overview['past_months'] if m['month'] == current_key)
        assert current['one_time_total'] == pytest.approx(200.0)   # 2 × 100
        # monthly 25×2=50 + yearly 600 on its anniversary month
        assert current['recurring_total'] == pytest.approx(650.0)
        assert overview['totals']['current_monthly_recurring'] == pytest.approx(50.0)
        assert len(overview['past_months']) == 12
        assert len(overview['projected_months']) == 12
        # every projected month carries the monthly sub
        assert all(m['recurring_total'] >= 50.0 for m in overview['projected_months'])


def test_overview_non_admin_scoped_to_own_data(bill_db):
    SessionLocal, admin, plain, tid = bill_db
    with SessionLocal() as db:
        overview = _svc(db).get_billing_overview(plain)
        assert overview['totals']['one_time_last_12_months'] == 0.0
        assert overview['totals']['recurring_last_12_months'] == 0.0


def test_overview_unknown_user_unauthorized(bill_db):
    from app.core.exceptions import UnauthorizedError
    SessionLocal, admin, plain, tid = bill_db
    with SessionLocal() as db:
        with pytest.raises(UnauthorizedError):
            _svc(db).get_billing_overview({'user_id': str(uuid.uuid4()),
                                           'tenant_id': str(tid), 'role': 'ADMIN'})


def test_overview_months_back_clamped(bill_db):
    SessionLocal, admin, plain, tid = bill_db
    with SessionLocal() as db:
        overview = _svc(db).get_billing_overview(admin, months_back=99, months_forward=99)
        assert len(overview['past_months']) == 24
        assert len(overview['projected_months']) == 24


def test_run_monthly_invoicing_requires_admin(bill_db):
    from app.core.exceptions import ForbiddenError
    SessionLocal, admin, plain, tid = bill_db
    with SessionLocal() as db:
        with pytest.raises(ForbiddenError):
            _svc(db).run_monthly_invoicing(plain)


def test_run_monthly_invoicing_creates_and_is_idempotent(bill_db):
    from app.models.lifecycle import InvoiceStatus
    SessionLocal, admin, plain, tid = bill_db
    month = date.today().replace(day=1)
    with SessionLocal() as db:
        svc = _svc(db)
        first = svc.run_monthly_invoicing(admin, billing_month=month)
        # monthly (50) + yearly anniversary (600); cancelled sub skipped
        assert len(first) == 2
        amounts = sorted(float(inv.amount) for inv in first)
        assert amounts == [50.0, 600.0]
        assert all(inv.status == InvoiceStatus.DUE for inv in first)
        assert all(inv.due_date == month + timedelta(days=14) for inv in first)
        second = svc.run_monthly_invoicing(admin, billing_month=month)
        assert {str(i.id) for i in second} == {str(i.id) for i in first}


def test_list_invoices_tenant_scoped_desc(bill_db):
    SessionLocal, admin, plain, tid = bill_db
    with SessionLocal() as db:
        svc = _svc(db)
        svc.run_monthly_invoicing(admin)
        invoices = svc.list_invoices(admin)
        assert invoices, 'expected invoices from the invoicing run'
        assert all(inv.tenant_id == tid for inv in invoices)


def test_record_payment_full_partial_and_errors(bill_db):
    from app.core.exceptions import AppError, ForbiddenError, NotFoundError
    from app.models.lifecycle import Invoice, InvoiceStatus, PaymentMethod
    SessionLocal, admin, plain, tid = bill_db
    month = date.today().replace(day=1)
    with SessionLocal() as db:
        svc = _svc(db)
        invoices = svc.run_monthly_invoicing(admin, billing_month=month)
        small = next(inv for inv in invoices if float(inv.amount) == 50.0)
        big = next(inv for inv in invoices if float(inv.amount) == 600.0)

        # full payment → PAID
        inv, payment = svc.record_payment(admin, str(small.id), amount=None,
                                          method=PaymentMethod.MANUAL)
        assert inv.status == InvoiceStatus.PAID
        assert inv.paid_at is not None
        assert float(payment.amount) == 50.0

        # partial payment → stays DUE
        inv2, _ = svc.record_payment(admin, str(big.id), amount=100.0,
                                     method=PaymentMethod.BANK_TRANSFER,
                                     external_reference='wire-1')
        assert inv2.status == InvoiceStatus.DUE

        # zero amount → 400
        with pytest.raises(AppError) as exc:
            svc.record_payment(admin, str(big.id), amount=0, method=PaymentMethod.MANUAL)
        assert exc.value.status_code == 400

        # VOID invoice → Forbidden
        void = Invoice(tenant_id=tid, billing_month=month, amount=10.0,
                       status=InvoiceStatus.VOID, currency='USD',
                       due_date=month + timedelta(days=14))
        db.add(void)
        db.commit()
        with pytest.raises(ForbiddenError):
            svc.record_payment(admin, str(void.id), amount=None, method=PaymentMethod.MANUAL)

        # unknown invoice → NotFound
        with pytest.raises(NotFoundError):
            svc.record_payment(admin, str(uuid.uuid4()), amount=None, method=PaymentMethod.MANUAL)
