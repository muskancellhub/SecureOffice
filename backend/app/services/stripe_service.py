import logging

import stripe
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.order import Order
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

_settings = get_settings()
stripe.api_key = _settings.stripe_secret_key


class StripeService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_customer(self, tenant: Tenant) -> str:
        if tenant.stripe_customer_id:
            return tenant.stripe_customer_id
        customer = stripe.Customer.create(
            name=tenant.name,
            metadata={'tenant_id': str(tenant.id)},
        )
        tenant.stripe_customer_id = customer.id
        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)
        return customer.id

    def create_subscription_checkout(self, tenant: Tenant, price_id: str) -> str:
        customer_id = self.get_or_create_customer(tenant)
        session = stripe.checkout.Session.create(
            mode='subscription',
            customer=customer_id,
            line_items=[{'price': price_id, 'quantity': 1}],
            success_url=_settings.stripe_success_url,
            cancel_url=_settings.stripe_cancel_url,
            client_reference_id=str(tenant.id),
        )
        return session.url

    def create_order_checkout(self, tenant: Tenant, order: Order) -> str:
        customer_id = self.get_or_create_customer(tenant)
        line_items = []
        for line in order.lines:
            unit_amount = int(round(float(line.final_unit_price_snapshot) * 100))
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': unit_amount,
                    'product_data': {'name': line.name_snapshot},
                },
                'quantity': line.qty,
            })
        session = stripe.checkout.Session.create(
            mode='payment',
            customer=customer_id,
            line_items=line_items,
            success_url=_settings.stripe_success_url,
            cancel_url=_settings.stripe_cancel_url,
            client_reference_id=str(tenant.id),
            metadata={'order_id': str(order.id), 'tenant_id': str(tenant.id)},
        )
        return session.url

    @staticmethod
    def verify_webhook(payload: bytes, sig_header: str) -> stripe.Event:
        return stripe.Webhook.construct_event(
            payload, sig_header, _settings.stripe_webhook_secret,
        )

    @staticmethod
    def retrieve_session(session_id: str) -> dict:
        session = stripe.checkout.Session.retrieve(session_id)
        return {
            'status': session.status,
            'payment_status': session.payment_status,
            'customer_email': session.customer_details.email if session.customer_details else None,
        }
