"""Unit tests for email-domain helpers (no DB, no network).

`domain_has_mail_exchange` (BUG-AUTH-010) is exercised against a fake DNS
resolver so the MX/A fallback and fail-open branches are covered deterministically.
"""
import dns.exception
import dns.resolver
import pytest

from app.core.email_domains import (
    domain_has_mail_exchange,
    extract_domain,
    is_free_email_provider,
)


def _patch_resolver(monkeypatch, behavior):
    """Install a fake dns.resolver.Resolver whose resolve(domain, rdtype) is
    driven by `behavior(rdtype)` — return a list of answers or raise."""
    class FakeResolver:
        def __init__(self):
            self.timeout = None
            self.lifetime = None

        def resolve(self, domain, rdtype):
            return behavior(rdtype)

    monkeypatch.setattr(dns.resolver, 'Resolver', FakeResolver)


def test_extract_domain_and_free_provider():
    assert extract_domain('A@B.Com') == 'b.com'
    assert extract_domain('no-at-sign') == ''
    assert is_free_email_provider('x@gmail.com') is True
    assert is_free_email_provider('x@acme.co') is False


def test_empty_domain_is_undeliverable():
    assert domain_has_mail_exchange('') is False


def test_mx_present_is_deliverable(monkeypatch):
    _patch_resolver(monkeypatch, lambda rdtype: ['mx1'] if rdtype == 'MX' else [])
    assert domain_has_mail_exchange('acme.co') is True


def test_no_mx_but_a_record_is_deliverable(monkeypatch):
    # RFC 5321 §5.1 implicit MX: no MX but an A record still receives mail.
    def behavior(rdtype):
        if rdtype == 'MX':
            raise dns.resolver.NoAnswer()
        if rdtype == 'A':
            return ['1.2.3.4']
        return []
    _patch_resolver(monkeypatch, behavior)
    assert domain_has_mail_exchange('acme.co') is True


def test_nxdomain_is_undeliverable(monkeypatch):
    def behavior(rdtype):
        raise dns.resolver.NXDOMAIN()
    _patch_resolver(monkeypatch, behavior)
    assert domain_has_mail_exchange('gmali-typo-xyz.com') is False


def test_domain_exists_but_no_records_is_undeliverable(monkeypatch):
    def behavior(rdtype):
        raise dns.resolver.NoAnswer()
    _patch_resolver(monkeypatch, behavior)
    assert domain_has_mail_exchange('acme.co') is False


def test_transient_dns_failure_fails_open(monkeypatch):
    # A resolver timeout must NOT block a legitimate signup.
    def behavior(rdtype):
        raise dns.exception.Timeout()
    _patch_resolver(monkeypatch, behavior)
    assert domain_has_mail_exchange('acme.co') is True
