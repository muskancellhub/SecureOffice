import uuid
import logging
from decimal import Decimal
from email_validator import EmailNotValidError, validate_email
from app.core.exceptions import AppError, NotFoundError, UnauthorizedError
from app.models.quote import BillingType
from app.repositories.onboarding_repository import OnboardingRepository
from app.repositories.order_notification_repository import OrderNotificationRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.quote_repository import QuoteRepository
from app.repositories.user_repository import UserRepository
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class OrderNotificationService:
    def __init__(self, db):
        self.db = db
        self.user_repo = UserRepository(db)
        self.order_repo = OrderRepository(db)
        self.quote_repo = QuoteRepository(db)
        self.onboarding_repo = OnboardingRepository(db)
        self.notification_repo = OrderNotificationRepository(db)

    @staticmethod
    def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            raise AppError(f'Invalid {field_name}', 400)

    def _assert_user_exists(self, current_user: dict) -> None:
        if not self.user_repo.get_by_id(current_user['user_id']):
            raise UnauthorizedError('User not found')

    @staticmethod
    def _normalize_recipients(recipients: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in recipients:
            value = str(raw or '').strip().lower()
            if not value:
                continue
            try:
                candidate = validate_email(value, check_deliverability=False).email.lower()
            except EmailNotValidError:
                raise AppError(f'Invalid recipient email: {value}', 422)
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return normalized

    def get_recipient_settings(self, current_user: dict):
        self._assert_user_exists(current_user)
        settings_row = self.notification_repo.get_or_create(current_user['tenant_id'])
        self.db.commit()
        self.db.refresh(settings_row)
        return settings_row

    def update_recipient_settings(self, current_user: dict, recipients: list[str]):
        self._assert_user_exists(current_user)
        settings_row = self.notification_repo.get_or_create(current_user['tenant_id'])
        normalized = self._normalize_recipients(recipients)
        settings_row.recipient_emails_json = normalized
        settings_row.updated_by_user_id = self._parse_uuid(current_user['user_id'], field_name='user_id')
        self.db.commit()
        self.db.refresh(settings_row)
        logger.warning(
            '[ORDER RECIPIENTS UPDATED] tenant_id=%s updated_by=%s recipients_count=%d recipients=%s',
            current_user.get('tenant_id'),
            current_user.get('user_id'),
            len(normalized),
            normalized,
        )
        return settings_row

    def list_recipients_for_tenant(self, tenant_id: str) -> list[str]:
        settings_row = self.notification_repo.get_by_tenant_id(tenant_id)
        if not settings_row:
            return []
        return self._normalize_recipients(list(settings_row.recipient_emails_json or []))

    @staticmethod
    def _compute_totals_from_order_lines(order) -> tuple[float, float, float]:
        one_time_total = Decimal('0')
        monthly_total = Decimal('0')
        for line in list(order.lines or []):
            line_total = Decimal(str(float(line.final_unit_price_snapshot))) * Decimal(str(int(line.qty)))
            if line.billing_type == BillingType.RECURRING:
                monthly_total += line_total
            else:
                one_time_total += line_total

        projected_12_month_cost = one_time_total + (monthly_total * Decimal('12'))
        return float(one_time_total), float(monthly_total), float(projected_12_month_cost)

    @staticmethod
    def _order_line_payload(line) -> dict:
        return {
            'name': line.name_snapshot,
            'sku': line.sku_snapshot,
            'vendor': line.vendor_snapshot,
            'qty': int(line.qty),
            'line_type': line.line_type.value if hasattr(line.line_type, 'value') else str(line.line_type),
            'billing': line.billing_type.value if hasattr(line.billing_type, 'value') else str(line.billing_type),
            'interval': line.interval.value if line.interval else None,
            'list_price_snapshot': float(line.list_price_snapshot),
            'final_unit_price_snapshot': float(line.final_unit_price_snapshot),
            'line_total': float(line.final_unit_price_snapshot) * int(line.qty),
        }

    def _build_order_payload(self, order) -> dict:
        quote = self.quote_repo.get_by_id(str(order.quote_id)) if order.quote_id else None
        creator = self.user_repo.get_by_id(str(order.created_by_user_id))
        onboarding = self.onboarding_repo.get_by_tenant_id(order.tenant_id)

        if quote:
            one_time_total = float(quote.one_time_total)
            monthly_total = float(quote.monthly_total)
            projected_12_month_cost = float(quote.projected_12_month_cost)
            currency = quote.currency
        else:
            one_time_total, monthly_total, projected_12_month_cost = self._compute_totals_from_order_lines(order)
            currency = 'USD'

        return {
            'order_id': order.public_id or str(order.id),
            'order_uuid': str(order.id),
            'quote_id': (quote.public_id if quote else None) or (str(order.quote_id) if order.quote_id else None),
            'quote_uuid': str(order.quote_id) if order.quote_id else None,
            'status': order.status.value if hasattr(order.status, 'value') else str(order.status),
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'estimated_delivery_date': order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else None,
            'confirmed_delivery_date': order.confirmed_delivery_date.isoformat() if order.confirmed_delivery_date else None,
            'customer': {
                'name': creator.name if creator else None,
                'email': creator.email if creator else None,
                'mobile': creator.mobile if creator else None,
                'organization_name': onboarding.organization_name if onboarding else None,
                'admin_name': onboarding.admin_name if onboarding else None,
                'admin_email': onboarding.admin_email if onboarding else None,
                'admin_phone': onboarding.admin_phone if onboarding else None,
            },
            'pricing': {
                'one_time_total': one_time_total,
                'monthly_total': monthly_total,
                'projected_12_month_cost': projected_12_month_cost,
                'currency': currency,
            },
            'line_items': [self._order_line_payload(line) for line in list(order.lines or [])],
        }

    def send_order_captured_notification(self, *, order_id: str) -> bool:
        logger.warning('[ORDER NOTIFICATION START] order_id=%s', order_id)
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError('Order not found')

        logger.warning(
            '[ORDER NOTIFICATION ORDER LOADED] order_id=%s tenant_id=%s quote_id=%s line_count=%d status=%s',
            order_id,
            str(order.tenant_id),
            str(order.quote_id) if order.quote_id else None,
            len(list(order.lines or [])),
            order.status.value if hasattr(order.status, 'value') else str(order.status),
        )
        recipients = self.list_recipients_for_tenant(str(order.tenant_id))
        logger.warning(
            '[ORDER NOTIFICATION RECIPIENTS] order_id=%s tenant_id=%s recipients_count=%d recipients=%s',
            order_id,
            str(order.tenant_id),
            len(recipients),
            recipients,
        )
        if not recipients:
            logger.warning('[SKIP ORDER HANDOFF] order_id=%s reason=no_configured_recipients', order_id)
            return False

        payload = self._build_order_payload(order)
        pricing = payload.get('pricing') or {}
        logger.warning(
            '[ORDER NOTIFICATION PAYLOAD READY] order_id=%s one_time_total=%s monthly_total=%s projected_12m=%s currency=%s',
            order_id,
            pricing.get('one_time_total'),
            pricing.get('monthly_total'),
            pricing.get('projected_12_month_cost'),
            pricing.get('currency'),
        )
        EmailService.send_order_capture_handoff(payload=payload, recipients=recipients)
        logger.warning('[ORDER NOTIFICATION DISPATCHED] order_id=%s recipients_count=%d', order_id, len(recipients))
        return True
