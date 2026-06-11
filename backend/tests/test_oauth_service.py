"""register_oauth_clients — conditional OAuth client registration."""
import app.services.oauth_service as oauth_module
from app.core.config import get_settings
from app.services.oauth_service import register_oauth_clients

settings = get_settings()


class RecordingOAuth:
    def __init__(self):
        self.registrations = []

    def register(self, **kwargs):
        self.registrations.append(kwargs)


def _patch_creds(monkeypatch, *, google=False, microsoft=False):
    monkeypatch.setattr(settings, 'google_client_id', 'gid' if google else '')
    monkeypatch.setattr(settings, 'google_client_secret', 'gsecret' if google else '')
    monkeypatch.setattr(settings, 'microsoft_client_id', 'mid' if microsoft else '')
    monkeypatch.setattr(settings, 'microsoft_client_secret', 'msecret' if microsoft else '')


def test_no_credentials_registers_nothing(monkeypatch):
    recorder = RecordingOAuth()
    monkeypatch.setattr(oauth_module, 'oauth', recorder)
    _patch_creds(monkeypatch)
    register_oauth_clients()
    assert recorder.registrations == []


def test_google_only(monkeypatch):
    recorder = RecordingOAuth()
    monkeypatch.setattr(oauth_module, 'oauth', recorder)
    _patch_creds(monkeypatch, google=True)
    register_oauth_clients()
    assert len(recorder.registrations) == 1
    reg = recorder.registrations[0]
    assert reg['name'] == 'google'
    assert 'accounts.google.com' in reg['server_metadata_url']
    assert reg['client_kwargs']['scope'] == 'openid email profile'


def test_microsoft_only_embeds_tenant_id(monkeypatch):
    recorder = RecordingOAuth()
    monkeypatch.setattr(oauth_module, 'oauth', recorder)
    _patch_creds(monkeypatch, microsoft=True)
    monkeypatch.setattr(settings, 'microsoft_tenant_id', 'contoso-tenant')
    register_oauth_clients()
    assert len(recorder.registrations) == 1
    reg = recorder.registrations[0]
    assert reg['name'] == 'microsoft'
    assert '/contoso-tenant/' in reg['server_metadata_url']
    assert 'User.Read' in reg['client_kwargs']['scope']


def test_both_providers(monkeypatch):
    recorder = RecordingOAuth()
    monkeypatch.setattr(oauth_module, 'oauth', recorder)
    _patch_creds(monkeypatch, google=True, microsoft=True)
    register_oauth_clients()
    assert [r['name'] for r in recorder.registrations] == ['google', 'microsoft']
