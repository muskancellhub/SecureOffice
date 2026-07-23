"""Unit tests for split-cadence tax estimation (BUG-MS-TAX-001/002).

No DB, no network — AvalaraService is monkeypatched so both the jurisdiction
path and the configured-rate fallback are covered deterministically.
"""
import app.services.tax_estimator as te
from app.services.avalara_service import AvalaraError, TaxQuote
from app.services.tax_estimator import address_from_dict, estimate_split_tax

ADDR = {'line1': '1 Main', 'city': 'Austin', 'state': 'TX', 'postal_code': '78701'}


def test_configured_fallback_taxes_both_cadences(monkeypatch):
    # Avalara not configured → use the configured percentage on BOTH cadences.
    monkeypatch.setattr(te.AvalaraService, 'is_configured', staticmethod(lambda: False))
    r = estimate_split_tax(one_time_subtotal=1000.0, recurring_subtotal=300.0,
                           ship_to=address_from_dict(ADDR), customer_code='t1', fallback_rate_pct=8.0)
    assert r.one_time.tax == 80.0 and r.one_time.total == 1080.0
    assert r.recurring.tax == 24.0 and r.recurring.total == 324.0  # $300/mo IS taxed
    assert r.one_time.source == 'configured'


def test_recurring_is_taxed_not_excluded(monkeypatch):
    # The core of MS-TAX-001: the monthly service must not be excluded from tax.
    monkeypatch.setattr(te.AvalaraService, 'is_configured', staticmethod(lambda: False))
    r = estimate_split_tax(one_time_subtotal=0.0, recurring_subtotal=300.0,
                           ship_to=None, customer_code='t1', fallback_rate_pct=8.0)
    assert r.recurring.subtotal == 300.0 and r.recurring.tax == 24.0


def test_avalara_used_when_configured(monkeypatch):
    monkeypatch.setattr(te.AvalaraService, 'is_configured', staticmethod(lambda: True))
    monkeypatch.setattr(te.AvalaraService, 'estimate_tax',
                        staticmethod(lambda **kw: TaxQuote(subtotal=kw['subtotal'], tax=12.34,
                                                           total=kw['subtotal'] + 12.34, breakdown=[{'j': 'TX'}])))
    r = estimate_split_tax(one_time_subtotal=1000.0, recurring_subtotal=0.0,
                           ship_to=address_from_dict(ADDR), customer_code='t1', fallback_rate_pct=8.0)
    assert r.one_time.tax == 12.34 and r.one_time.source == 'avalara'
    assert r.breakdown == [{'j': 'TX'}]


def test_avalara_error_falls_back_to_rate(monkeypatch):
    monkeypatch.setattr(te.AvalaraService, 'is_configured', staticmethod(lambda: True))
    def boom(**kw):
        raise AvalaraError('boom')
    monkeypatch.setattr(te.AvalaraService, 'estimate_tax', staticmethod(boom))
    r = estimate_split_tax(one_time_subtotal=500.0, recurring_subtotal=0.0,
                           ship_to=address_from_dict(ADDR), customer_code='t1', fallback_rate_pct=10.0)
    assert r.one_time.tax == 50.0 and r.one_time.source == 'configured'


def test_zero_subtotal_is_untaxed(monkeypatch):
    monkeypatch.setattr(te.AvalaraService, 'is_configured', staticmethod(lambda: False))
    r = estimate_split_tax(one_time_subtotal=0.0, recurring_subtotal=0.0,
                           ship_to=None, customer_code='t1', fallback_rate_pct=8.0)
    assert r.one_time.total == 0.0 and r.recurring.total == 0.0


def test_address_from_dict_requires_state_and_zip():
    assert address_from_dict({'city': 'Austin'}) is None       # missing state+zip
    assert address_from_dict({'state': 'TX', 'postal_code': '78701'}) is not None
    assert address_from_dict(None) is None
