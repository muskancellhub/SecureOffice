"""Zabbix monitoring proxy routes.

Read endpoints require an authenticated user but no special permission,
making the Zabbix dashboard visible to every logged-in user. Credential
configuration endpoints are restricted to admins.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.middleware.dependencies import get_current_user
from app.services.audit_logger import audit
from app.services.zabbix_client import (
    ZabbixClient,
    get_runtime_credentials_status,
    set_runtime_credentials,
)

router = APIRouter(prefix='/zabbix', tags=['Zabbix'])

_ADMIN_ROLES = {'ADMIN', 'SUPER_ADMIN'}


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    role = str(current_user.get('role') or '').upper()
    if role not in _ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin only')
    return current_user


def _client() -> ZabbixClient:
    return ZabbixClient()


class ZabbixCredentialsIn(BaseModel):
    url: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


@router.get('/config')
def zabbix_get_config(_admin: dict = Depends(_require_admin)):
    """Admin only: return whether Zabbix credentials are configured (no secrets)."""
    return get_runtime_credentials_status()


@router.post('/config')
def zabbix_set_config(payload: ZabbixCredentialsIn, _admin: dict = Depends(_require_admin)):
    """Admin only: set Zabbix credentials at runtime and verify by syncing.

    The credentials replace any env-based config for the rest of the process
    lifetime. We immediately attempt a dashboard fetch to validate them; if
    that fails the credentials are rejected.
    """
    set_runtime_credentials(payload.url, payload.username, payload.password)
    try:
        summary = ZabbixClient().get_dashboard_summary()
    except Exception as exc:
        # Roll back so a bad credential doesn't break monitoring for everyone
        set_runtime_credentials('', '', '')
        # url/username only — the password must never reach a log line (plan §6).
        audit.log('zabbix_credentials_updated', status='failure', level=logging.WARNING,
                  url=payload.url, zabbix_username=payload.username, reason='validation_failed')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Zabbix sync failed: {exc}',
        )
    audit.log('zabbix_credentials_updated', url=payload.url, zabbix_username=payload.username)
    return {
        'status': 'ok',
        'config': get_runtime_credentials_status(),
        'summary': summary,
    }


@router.get('/dashboard')
def zabbix_dashboard(current_user: dict = Depends(get_current_user)):
    """Aggregated KPI summary: host counts, problems by severity, trigger count."""
    return _client().get_dashboard_summary()


@router.get('/hosts')
def zabbix_hosts(current_user: dict = Depends(get_current_user)):
    """List monitored hosts with interface info."""
    return _client().get_hosts()


@router.get('/problems')
def zabbix_problems(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """Active problems sorted by severity."""
    return _client().get_problems(limit=limit)


@router.get('/triggers')
def zabbix_triggers(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """Active triggers with host association."""
    return _client().get_triggers(limit=limit)


@router.get('/hosts/{host_id}/metrics')
def zabbix_host_metrics(
    host_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Key metric items for a specific host."""
    return _client().get_host_metrics(host_id)
