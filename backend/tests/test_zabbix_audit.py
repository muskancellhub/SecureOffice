"""BUG-AUD-018 — zabbix_credentials_updated uses spec field names
(url_set / validation_status), and never logs the password."""

import logging

import pytest

from app.core.logging_config import SD_ID_AUDIT
from app.routes import zabbix


class _OkClient:
    def get_dashboard_summary(self):
        return {}


class _BadClient:
    def get_dashboard_summary(self):
        raise RuntimeError('unreachable')


def _capture():
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    lg = logging.getLogger('secureoffice.audit')
    lg.addHandler(handler)
    lg.setLevel(logging.INFO)
    return records, handler, lg


def _event(records):
    rec = next(r for r in records if getattr(r, 'msgid', None) == 'zabbix_credentials_updated')
    return rec.sd[SD_ID_AUDIT]


def test_zabbix_success_uses_spec_fields(monkeypatch):
    monkeypatch.setattr(zabbix, 'set_runtime_credentials', lambda u, n, p: None)
    monkeypatch.setattr(zabbix, 'ZabbixClient', _OkClient)
    payload = zabbix.ZabbixCredentialsIn(url='https://zbx.example', username='admin',
                                         password='secret-pass')
    records, handler, lg = _capture()
    try:
        zabbix.zabbix_set_config(payload, _admin={'role': 'SUPER_ADMIN'})
    finally:
        lg.removeHandler(handler)

    f = _event(records)
    assert f['url_set'] == 'https://zbx.example'
    assert f['validation_status'] == 'success'
    assert 'url' not in f and 'reason' not in f
    assert 'secret-pass' not in str(f)  # password never logged


def test_zabbix_failure_uses_spec_fields(monkeypatch):
    monkeypatch.setattr(zabbix, 'set_runtime_credentials', lambda u, n, p: None)
    monkeypatch.setattr(zabbix, 'ZabbixClient', _BadClient)
    payload = zabbix.ZabbixCredentialsIn(url='https://zbx.example', username='admin',
                                         password='secret-pass')
    records, handler, lg = _capture()
    try:
        with pytest.raises(Exception):
            zabbix.zabbix_set_config(payload, _admin={'role': 'SUPER_ADMIN'})
    finally:
        lg.removeHandler(handler)

    f = _event(records)
    assert f['url_set'] == 'https://zbx.example'
    assert f['validation_status'] == 'failed'
    assert 'reason' not in f
    assert 'secret-pass' not in str(f)
