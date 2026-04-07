import uuid
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.models.lifecycle import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)
from app.models.order import Order, OrderLine
from app.models.quote import BillingInterval, BillingType
from app.models.user import UserRole
from app.repositories.user_repository import UserRepository


class BillingService:
    def __init__(self, db):
        self.db = db
        self.user_repo = UserRepository(db)

    @staticmethod
    def _add_months(source: date, months: int) -> date:
        month_index = source.month - 1 + months
        year = source.year + month_index // 12
        month = month_index % 12 + 1
        return date(year, month, 1)

    @staticmethod
    def _month_key(month_date: date) -> str:
        return f'{month_date.year:04d}-{month_date.month:02d}'

    @staticmethod
    def _is_admin(role: str | None) -> bool:
        return role in {UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value}

    @staticmethod
    def _is_active_for_month(subscription: Subscription, month_start: date) -> bool:
        month_end = BillingService._add_months(month_start, 1) - timedelta(days=1)
        if subscription.start_date and subscription.start_date > month_end:
            return False
        if subscription.end_date and subscription.end_date < month_start:
            return False
        return subscription.status == SubscriptionStatus.ACTIVE

    @staticmethod
    def _recurring_charge_for_month(subscription: Subscription, month_start: date) -> float:
        if subscription.interval == BillingInterval.MONTH:
            return float(subscription.unit_price) * subscription.qty
        if subscription.interval == BillingInterval.YEAR and subscription.start_date.month == month_start.month:
            return float(subscription.unit_price) * subscription.qty
        return 0.0

    @staticmethod
    def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except (ValueError, TypeError):
            raise NotFoundError(f'Invalid {field_name}')

    def _assert_user_exists(self, current_user: dict):
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found')

    def _assert_admin(self, current_user: dict) -> None:
        if not self._is_admin(current_user.get('role')):
            raise ForbiddenError('Only ADMIN or SUPER_ADMIN can perform billing admin actions')

    def _tenant_id(self, current_user: dict) -> uuid.UUID:
        return self._parse_uuid(current_user['tenant_id'], field_name='tenant_id')

    def get_billing_overview(self, current_user: dict, months_back: int = 12, months_forward: int = 12) -> dict:
        self._assert_user_exists(current_user)
        tenant_id = self._tenant_id(current_user)
        months_back = max(1, min(months_back, 24))
        months_forward = max(1, min(months_forward, 24))

        current_month = date.today().replace(day=1)
        past_start = self._add_months(current_month, -(months_back - 1))
        future_start = self._add_months(current_month, 1)

        past_months = [self._add_months(past_start, i) for i in range(months_back)]
        projected_months = [self._add_months(future_start, i) for i in range(months_forward)]

        past_map = {
            self._month_key(month): {'month': self._month_key(month), 'one_time_total': 0.0, 'recurring_total': 0.0, 'total': 0.0}
            for month in past_months
        }
        projected_map = {
            self._month_key(month): {'month': self._month_key(month), 'one_time_total': 0.0, 'recurring_total': 0.0, 'total': 0.0}
            for month in projected_months
        }

        order_rows = self.db.execute(
            select(Order.created_at, OrderLine.unit_price, OrderLine.qty)
            .join(OrderLine, OrderLine.order_id == Order.id)
            .where(
                Order.tenant_id == tenant_id,
                OrderLine.billing == BillingType.ONE_TIME,
                Order.created_at >= datetime.combine(past_start, datetime.min.time(), timezone.utc),
            )
        ).all()

        for created_at, unit_price, qty in order_rows:
            month_key = self._month_key(created_at.date().replace(day=1))
            if month_key not in past_map:
                continue
            amount = float(unit_price) * qty
            past_map[month_key]['one_time_total'] += amount
            past_map[month_key]['total'] += amount

        subscriptions = list(
            self.db.scalars(
                select(Subscription)
                .where(Subscription.tenant_id == tenant_id)
                .order_by(desc(Subscription.created_at))
            ).all()
        )

        for month in past_months:
            month_key = self._month_key(month)
            recurring_total = 0.0
            for subscription in subscriptions:
                if not self._is_active_for_month(subscription, month):
                    continue
                recurring_total += self._recurring_charge_for_month(subscription, month)
            past_map[month_key]['recurring_total'] += recurring_total
            past_map[month_key]['total'] += recurring_total

        for month in projected_months:
            month_key = self._month_key(month)
            recurring_total = 0.0
            for subscription in subscriptions:
                if not self._is_active_for_month(subscription, month):
                    continue
                recurring_total += self._recurring_charge_for_month(subscription, month)
            projected_map[month_key]['recurring_total'] += recurring_total
            projected_map[month_key]['total'] += recurring_total

        current_monthly_recurring = sum(
            float(subscription.unit_price) * subscription.qty
            for subscription in subscriptions
            if subscription.status == SubscriptionStatus.ACTIVE and subscription.interval == BillingInterval.MONTH
        )

        past_values = [past_map[self._month_key(month)] for month in past_months]
        projected_values = [projected_map[self._month_key(month)] for month in projected_months]

        return {
            'past_months': past_values,
            'projected_months': projected_values,
            'totals': {
                'one_time_last_12_months': sum(item['one_time_total'] for item in past_values),
                'recurring_last_12_months': sum(item['recurring_total'] for item in past_values),
                'projected_next_12_months': sum(item['total'] for item in projected_values),
                'current_monthly_recurring': current_monthly_recurring,
            },
        }

    def list_invoices(self, current_user: dict) -> list[Invoice]:
        self._assert_user_exists(current_user)
        tenant_id = self._tenant_id(current_user)
        stmt = (
            select(Invoice)
            .where(Invoice.tenant_id == tenant_id)
            .options(selectinload(Invoice.payments))
            .order_by(desc(Invoice.issued_at))
        )
        return list(self.db.scalars(stmt).all())

    def run_monthly_invoicing(self, current_user: dict, billing_month: date | None = None) -> list[Invoice]:
        self._assert_user_exists(current_user)
        self._assert_admin(current_user)
        tenant_id = self._tenant_id(current_user)
        month_start = (billing_month or date.today()).replace(day=1)

        subscriptions = list(
            self.db.scalars(
                select(Subscription).where(
                    Subscription.tenant_id == tenant_id,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            ).all()
        )

        created_or_existing: list[Invoice] = []
        for subscription in subscriptions:
            if not self._is_active_for_month(subscription, month_start):
                continue
            amount = self._recurring_charge_for_month(subscription, month_start)
            if amount <= 0:
                continue

            existing = self.db.scalar(
                select(Invoice).where(
                    Invoice.subscription_id == subscription.id,
                    Invoice.billing_month == month_start,
                )
            )
            if existing:
                created_or_existing.append(existing)
                continue

            invoice = Invoice(
                tenant_id=tenant_id,
                subscription_id=subscription.id,
                billing_month=month_start,
                amount=amount,
                currency=subscription.currency,
                status=InvoiceStatus.DUE,
                due_date=month_start + timedelta(days=14),
                metadata_json={'source': 'monthly_invoicing_run'},
            )
            self.db.add(invoice)
            self.db.flush()
            created_or_existing.append(invoice)

        self.db.commit()
        return created_or_existing

    def record_payment(
        self,
        current_user: dict,
        invoice_id: str,
        *,
        amount: float | None,
        method: PaymentMethod,
        external_reference: str | None = None,
    ) -> tuple[Invoice, Payment]:
        self._assert_user_exists(current_user)
        self._assert_admin(current_user)
        tenant_id = self._tenant_id(current_user)
        invoice_uuid = self._parse_uuid(invoice_id, field_name='invoice_id')

        invoice = self.db.get(Invoice, invoice_uuid)
        if not invoice or invoice.tenant_id != tenant_id:
            raise NotFoundError('Invoice not found')
        if invoice.status == InvoiceStatus.VOID:
            raise ForbiddenError('Cannot record payment for void invoice')

        payment_amount = float(amount) if amount is not None else float(invoice.amount)
        payment = Payment(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            amount=payment_amount,
            currency=invoice.currency,
            status=PaymentStatus.SUCCEEDED,
            method=method,
            external_reference=external_reference,
            metadata_json={},
        )
        self.db.add(payment)

        if payment_amount >= float(invoice.amount):
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(invoice)
        self.db.refresh(payment)
        return invoice, payment
