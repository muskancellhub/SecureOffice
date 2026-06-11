"""StripeService — unit tests with the stripe SDK fully monkeypatched (no network)."""
import uuid
from types import SimpleNamespace

import pytest
import stripe

from app.core.config import get_settings
from app.models.tenant import Tenant
from app.services.stripe_service import StripeService

settings = get_settings()


class FakeDB:
    def add(self, obj):
        pass

    def commit(self):
        pass

    def refresh(self, obj):
        pass


def _tenant(customer_id=None):
    return Tenant(id=uuid.uuid4(), name='Stripe Test Co', stripe_customer_id=customer_id)


def test_get_or_create_customer_short_circuits_on_existing(monkeypatch):
    def boom(**kwargs):
        raise AssertionError('Customer.create must not be called')
    monkeypatch.setattr(stripe.Customer, 'create', boom)
    svc = StripeService(FakeDB())
    assert svc.get_or_create_customer(_tenant('cus_existing')) == 'cus_existing'


def test_get_or_create_customer_creates_and_persists(monkeypatch):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id='cus_new123')
    monkeypatch.setattr(stripe.Customer, 'create', fake_create)
    tenant = _tenant()
    svc = StripeService(FakeDB())
    assert svc.get_or_create_customer(tenant) == 'cus_new123'
    assert tenant.stripe_customer_id == 'cus_new123'
    assert captured['name'] == 'Stripe Test Co'
    assert captured['metadata'] == {'tenant_id': str(tenant.id)}


def test_create_subscription_checkout_args(monkeypatch):
    captured = {}

    def fake_session_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url='https://checkout.stripe.test/sub')
    monkeypatch.setattr(stripe.checkout.Session, 'create', fake_session_create)
    tenant = _tenant('cus_1')
    url = StripeService(FakeDB()).create_subscription_checkout(tenant, 'price_abc')
    assert url == 'https://checkout.stripe.test/sub'
    assert captured['mode'] == 'subscription'
    assert captured['customer'] == 'cus_1'
    assert captured['line_items'] == [{'price': 'price_abc', 'quantity': 1}]
    assert captured['client_reference_id'] == str(tenant.id)
    assert captured['success_url'] == settings.stripe_success_url
    assert captured['cancel_url'] == settings.stripe_cancel_url


def _order_with_lines(*prices_and_qtys):
    lines = [
        SimpleNamespace(final_unit_price_snapshot=price, name_snapshot=f'Item {i}', qty=qty)
        for i, (price, qty) in enumerate(prices_and_qtys)
    ]
    return SimpleNamespace(id=uuid.uuid4(), lines=lines)


def test_create_order_checkout_builds_price_data(monkeypatch):
    captured = {}

    def fake_session_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(url='https://checkout.stripe.test/order')
    monkeypatch.setattr(stripe.checkout.Session, 'create', fake_session_create)
    tenant = _tenant('cus_1')
    order = _order_with_lines((125.50, 2), (3.00, 1))
    url = StripeService(FakeDB()).create_order_checkout(tenant, order)
    assert url == 'https://checkout.stripe.test/order'
    assert captured['mode'] == 'payment'
    assert captured['metadata'] == {'order_id': str(order.id), 'tenant_id': str(tenant.id)}
    li = captured['line_items']
    assert li[0]['price_data']['unit_amount'] == 12550
    assert li[0]['price_data']['currency'] == 'usd'
    assert li[0]['price_data']['product_data']['name'] == 'Item 0'
    assert li[0]['quantity'] == 2
    assert li[1]['price_data']['unit_amount'] == 300


def test_order_checkout_cents_rounding(monkeypatch):
    captured = {}
    monkeypatch.setattr(stripe.checkout.Session, 'create',
                        lambda **kw: captured.update(kw) or SimpleNamespace(url='u'))
    order = _order_with_lines((19.999, 1))
    StripeService(FakeDB()).create_order_checkout(_tenant('cus_1'), order)
    assert captured['line_items'][0]['price_data']['unit_amount'] == 2000


def test_verify_webhook_passes_through(monkeypatch):
    captured = {}
    sentinel = object()

    def fake_construct(payload, sig, secret):
        captured.update(payload=payload, sig=sig, secret=secret)
        return sentinel
    monkeypatch.setattr(stripe.Webhook, 'construct_event', staticmethod(fake_construct))
    result = StripeService.verify_webhook(b'{"x":1}', 'sig_header_v1')
    assert result is sentinel
    assert captured == {'payload': b'{"x":1}', 'sig': 'sig_header_v1',
                        'secret': settings.stripe_webhook_secret}


def test_retrieve_session_maps_fields(monkeypatch):
    fake = SimpleNamespace(status='complete', payment_status='paid',
                           customer_details=SimpleNamespace(email='buyer@corp.com'))
    monkeypatch.setattr(stripe.checkout.Session, 'retrieve', lambda sid: fake)
    out = StripeService.retrieve_session('cs_123')
    assert out == {'status': 'complete', 'payment_status': 'paid',
                   'customer_email': 'buyer@corp.com'}


def test_retrieve_session_handles_missing_customer_details(monkeypatch):
    fake = SimpleNamespace(status='open', payment_status='unpaid', customer_details=None)
    monkeypatch.setattr(stripe.checkout.Session, 'retrieve', lambda sid: fake)
    assert StripeService.retrieve_session('cs_123')['customer_email'] is None
