"""Tests for the Resend-backed EmailService.

Covers the live send path (resend.Emails.send monkeypatched) and the mock path
when RESEND_API_KEY is absent.
"""
import resend

from app.services import email_service as email_module
from app.services.email_service import EmailService


def _patch_resend(monkeypatch, *, api_key='re_test', from_email='no-reply@example.com', from_name='CellHub'):
    """Point EmailService at a fake settings object with Resend configured."""
    settings = email_module.settings
    monkeypatch.setattr(settings, 'resend_api_key', api_key, raising=False)
    monkeypatch.setattr(settings, 'resend_from_email', from_email, raising=False)
    monkeypatch.setattr(settings, 'resend_from_name', from_name, raising=False)


def test_send_otp_email_calls_resend(monkeypatch):
    _patch_resend(monkeypatch)
    captured = {}

    def fake_send(params):
        captured['params'] = params
        return {'id': 'test_otp_123'}

    monkeypatch.setattr(resend.Emails, 'send', staticmethod(fake_send))

    EmailService.send_otp_email(to_email='user@example.com', otp='123456', purpose='login')

    params = captured['params']
    assert params['from'] == 'CellHub <no-reply@example.com>'
    assert params['to'] == ['user@example.com']
    assert 'OTP for login' in params['subject']
    assert '123456' in params['html']
    assert '123456' in params['text']


def test_send_order_capture_calls_resend(monkeypatch):
    _patch_resend(monkeypatch)
    captured = {}

    def fake_send(params):
        captured['params'] = params
        return {'id': 'test_order_456'}

    monkeypatch.setattr(resend.Emails, 'send', staticmethod(fake_send))

    payload = {'order_id': 'ORD-1', 'status': 'captured', 'line_items': []}
    EmailService.send_order_capture_handoff(
        payload=payload,
        recipients=['ops@example.com', 'OPS@example.com', ' '],
    )

    params = captured['params']
    # deduped + normalized recipients
    assert params['to'] == ['ops@example.com']
    assert params['subject'] == 'Order Captured: ORD-1'


def test_send_design_submission_calls_resend(monkeypatch):
    _patch_resend(monkeypatch)
    monkeypatch.setattr(email_module.settings, 'design_handoff_email', 'design@example.com', raising=False)
    captured = {}

    def fake_send(params):
        captured['params'] = params
        return {'id': 'test_design_789'}

    monkeypatch.setattr(resend.Emails, 'send', staticmethod(fake_send))

    EmailService.send_design_submission_handoff({'design_id': 'D-1', 'design_name': 'Branch Office'})

    params = captured['params']
    assert params['to'] == ['design@example.com']
    assert 'Branch Office' in params['subject']


def test_mock_path_when_key_absent(monkeypatch):
    """No RESEND_API_KEY -> mock path: no exception, resend.Emails.send never called."""
    _patch_resend(monkeypatch, api_key='')

    def boom(_params):  # pragma: no cover - must not be called
        raise AssertionError('resend.Emails.send must not be called on the mock path')

    monkeypatch.setattr(resend.Emails, 'send', staticmethod(boom))

    # all three senders should no-op cleanly
    EmailService.send_otp_email(to_email='user@example.com', otp='000000', purpose='login')
    EmailService.send_order_capture_handoff(payload={'order_id': 'ORD-2'}, recipients=['ops@example.com'])
    EmailService.send_design_submission_handoff({'design_id': 'D-2'})
