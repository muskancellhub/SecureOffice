"""Zabbix monitoring proxy routes.

All endpoints require an authenticated user but no special permission,
making the Zabbix dashboard visible to every logged-in user.
"""

from fastapi import APIRouter, Depends

from app.middleware.dependencies import get_current_user
from app.services.zabbix_client import ZabbixClient

router = APIRouter(prefix='/zabbix', tags=['Zabbix'])


def _client() -> ZabbixClient:
    return ZabbixClient()


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
