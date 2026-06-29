"""SquareService — unit tests with httpx fully monkeypatched (no network)."""
import base64
import hashlib
import hmac
import uuid
from types import SimpleNamespace

import pytest

import app.services.square_service as sq
from app.services.square_service import SquareError, SquareService


class FakeDB:
    def add(self, obj):
        pass

    def commit(self):
        pass

    def flush(self):
        pass


class FakeResp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def _line(price, qty, billing='ONE_TIME'):
    return SimpleNamespace(final_unit_price_snapshot=price, name_snapshot='Item',
                           qty=qty, billing_type=billing)


def _order(*prices_and_qtys, tenant_id=None, public_id='OID0007'):
    # Each tuple is (price, qty) or (price, qty, billing). Defaults to ONE_TIME.
    lines = [_line(*pq) for pq in prices_and_qtys]
    return SimpleNamespace(id=uuid.uuid4(), tenant_id=tenant_id or uuid.uuid4(),
                           public_id=public_id, lines=lines)


def test_order_amount_cents_sums_and_rounds():
    order = _order((125.50, 2), (3.00, 1), (19.999, 1))
    # unit_amount*qty: 12550*2=25100, 300*1=300, 2000*1=2000
    assert SquareService.order_amount_cents(order) == 25100 + 300 + 2000


def test_order_amount_cents_excludes_recurring():
    # Recurring lines are billed monthly by the invoicing engine, not charged
    # upfront — only the one-time lines count toward the card charge.
    order = _order((500.00, 1, 'ONE_TIME'), (12.50, 10, 'RECURRING'), (350.00, 1, 'ONE_TIME'))
    assert SquareService.order_amount_cents(order) == 50000 + 35000


def test_create_payment_builds_request_and_returns_payment(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return FakeResp(200, {'payment': {'id': 'sqpay_1', 'status': 'COMPLETED',
                                          'amount_money': {'amount': 25400, 'currency': 'USD'}}})
    monkeypatch.setattr(sq.httpx, 'post', fake_post)
    order = _order((125.50, 2), (3.00, 1))  # 25100 + 300 = 25400
    payment = SquareService(FakeDB()).create_payment(order, 'cnon_nonce', 'idem-123')

    assert payment['id'] == 'sqpay_1'
    assert captured['url'].endswith('/v2/payments')
    assert captured['headers']['Square-Version'] == sq._settings.square_version
    assert captured['headers']['Authorization'].startswith('Bearer ')
    body = captured['json']
    assert body['source_id'] == 'cnon_nonce'
    assert body['idempotency_key'] == 'idem-123'
    assert body['amount_money'] == {'amount': 25400, 'currency': 'USD'}
    assert body['reference_id'] == str(order.id)
    assert body['autocomplete'] is True


def test_create_payment_raises_square_error_on_failure(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResp(402, {'errors': [{'category': 'PAYMENT_METHOD_ERROR',
                                          'code': 'CARD_DECLINED', 'detail': 'Card declined.'}]})
    monkeypatch.setattr(sq.httpx, 'post', fake_post)
    with pytest.raises(SquareError) as exc:
        SquareService(FakeDB()).create_payment(_order((10.0, 1)), 'cnon_bad', 'idem-x')
    assert exc.value.status_code == 402
    assert 'CARD_DECLINED' in str(exc.value)


def test_get_payment_returns_payment(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        assert url.endswith('/v2/payments/sqpay_9')
        return FakeResp(200, {'payment': {'id': 'sqpay_9', 'status': 'COMPLETED'}})
    monkeypatch.setattr(sq.httpx, 'get', fake_get)
    assert SquareService(FakeDB()).get_payment('sqpay_9')['status'] == 'COMPLETED'


def test_verify_webhook_accepts_valid_signature(monkeypatch):
    monkeypatch.setattr(sq._settings, 'square_webhook_signature_key', 'whsk_test')
    url = 'https://tunnel.example/billing/square/webhook'
    body = b'{"type":"payment.updated"}'
    mac = hmac.new(b'whsk_test', url.encode() + body, hashlib.sha256).digest()
    sig = base64.b64encode(mac).decode()
    assert SquareService.verify_webhook(body, sig, url) is True
    # tampered body fails
    assert SquareService.verify_webhook(b'{"type":"x"}', sig, url) is False
    # wrong url fails
    assert SquareService.verify_webhook(body, sig, 'https://evil/x') is False


def test_verify_webhook_rejects_when_key_or_sig_missing(monkeypatch):
    monkeypatch.setattr(sq._settings, 'square_webhook_signature_key', '')
    assert SquareService.verify_webhook(b'{}', 'sig', 'u') is False
    monkeypatch.setattr(sq._settings, 'square_webhook_signature_key', 'k')
    assert SquareService.verify_webhook(b'{}', '', 'u') is False


def test_is_paid_status():
    assert SquareService.is_paid_status('COMPLETED') is True
    assert SquareService.is_paid_status('APPROVED') is True
    assert SquareService.is_paid_status('PENDING') is False
    assert SquareService.is_paid_status(None) is False
