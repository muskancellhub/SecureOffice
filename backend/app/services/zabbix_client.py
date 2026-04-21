"""Zabbix JSON-RPC API client.

Authenticates via ``user.login`` (username + password) and caches the
session token in-memory.  The token is refreshed automatically when it
expires or becomes invalid.

Configuration is read from environment variables via ``get_settings()``:
  ZABBIX_URL       – e.g. https://zabbix.example.com
  ZABBIX_USERNAME  – Zabbix web user
  ZABBIX_PASSWORD  – Zabbix web password
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

# ── module-level session cache ────────────────────────────────────────
_cached_auth_token: str | None = None
_token_obtained_at: float = 0
_TOKEN_TTL_SECONDS = 25 * 60  # re-login every 25 min (Zabbix default session = 30 min)

_REQ_ID = 0


def _next_id() -> int:
    global _REQ_ID
    _REQ_ID += 1
    return _REQ_ID


def _raw_rpc(api_url: str, method: str, params: dict, auth: str | None = None) -> Any:
    """Fire a single JSON-RPC 2.0 call and return the ``result`` field."""
    payload: dict[str, Any] = {
        'jsonrpc': '2.0',
        'method': method,
        'params': params,
        'id': _next_id(),
    }
    if auth is not None:
        payload['auth'] = auth

    headers = {'Content-Type': 'application/json'}

    try:
        resp = httpx.post(api_url, json=payload, headers=headers, timeout=30)
    except httpx.RequestError as exc:
        logger.error('Zabbix request failed: %s', exc)
        raise AppError(f'Cannot reach Zabbix server: {exc}', 502)

    if resp.status_code != 200:
        raise AppError(f'Zabbix returned HTTP {resp.status_code}', 502)

    body = resp.json()
    if 'error' in body:
        err = body['error']
        msg = err.get('data', err.get('message', str(err)))
        raise AppError(f'Zabbix API error: {msg}', 502)

    return body.get('result')


class ZabbixClient:
    """Thin wrapper around the Zabbix JSON-RPC endpoint.

    Uses ``user.login`` to obtain a session token, then passes it in the
    ``auth`` field of every subsequent request.  The token is cached at
    module level so it survives across requests.
    """

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.zabbix_url or not settings.zabbix_username or not settings.zabbix_password:
            raise AppError(
                'Zabbix is not configured. Set ZABBIX_URL, ZABBIX_USERNAME, and ZABBIX_PASSWORD.',
                503,
            )
        self.api_url = settings.zabbix_url.rstrip('/') + '/api_jsonrpc.php'
        self._username = settings.zabbix_username
        self._password = settings.zabbix_password
        self._auth = self._ensure_token()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def _ensure_token(self) -> str:
        global _cached_auth_token, _token_obtained_at

        if _cached_auth_token and (time.time() - _token_obtained_at) < _TOKEN_TTL_SECONDS:
            return _cached_auth_token

        logger.info('Zabbix: obtaining new session token via user.login')
        try:
            token = _raw_rpc(
                self.api_url,
                'user.login',
                {'username': self._username, 'password': self._password},
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(f'Zabbix login failed: {exc}', 502)

        if not token or not isinstance(token, str):
            raise AppError('Zabbix user.login returned an invalid token', 502)

        _cached_auth_token = token
        _token_obtained_at = time.time()
        return token

    def _invalidate_token(self) -> None:
        global _cached_auth_token, _token_obtained_at
        _cached_auth_token = None
        _token_obtained_at = 0

    # ------------------------------------------------------------------
    # Low-level RPC helper (with auto-retry on auth failure)
    # ------------------------------------------------------------------
    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        try:
            return _raw_rpc(self.api_url, method, params or {}, auth=self._auth)
        except AppError as exc:
            # If the token expired mid-session, retry once with a fresh login
            if 'Not authorised' in str(exc) or 'Session terminated' in str(exc):
                logger.warning('Zabbix session expired – re-authenticating')
                self._invalidate_token()
                self._auth = self._ensure_token()
                return _raw_rpc(self.api_url, method, params or {}, auth=self._auth)
            raise

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    def get_hosts(self) -> list[dict]:
        """Return monitored hosts with interface info."""
        return self.call('host.get', {
            'output': ['hostid', 'host', 'name', 'status', 'available',
                        'description', 'maintenance_status'],
            'selectInterfaces': ['ip', 'port', 'type', 'main'],
            'selectHostGroups': ['groupid', 'name'],
            'sortfield': 'name',
            'monitored_hosts': True,
        })

    def get_problems(self, limit: int = 100) -> list[dict]:
        """Return recent active problems sorted by severity (desc).

        ``problem.get`` does not support ``selectHosts``, so we resolve
        host names via the trigger ``objectid`` using ``trigger.get``.
        """
        problems = self.call('problem.get', {
            'output': ['eventid', 'objectid', 'name', 'severity', 'acknowledged',
                        'clock', 'r_eventid', 'r_clock'],
            'selectTags': 'extend',
            'recent': True,
            'sortfield': 'eventid',
            'sortorder': 'DESC',
            'limit': limit,
        })

        # Resolve host names from trigger objectids
        trigger_ids = list({p['objectid'] for p in problems if p.get('objectid')})
        host_map: dict[str, list[dict]] = {}
        if trigger_ids:
            triggers = self.call('trigger.get', {
                'triggerids': trigger_ids,
                'output': ['triggerid'],
                'selectHosts': ['hostid', 'name'],
            })
            for t in triggers:
                host_map[t['triggerid']] = t.get('hosts', [])

        for p in problems:
            p['hosts'] = host_map.get(p.get('objectid', ''), [])

        return problems

    def get_triggers(self, limit: int = 100) -> list[dict]:
        """Return active triggers with host info."""
        return self.call('trigger.get', {
            'output': ['triggerid', 'description', 'priority', 'status',
                        'value', 'lastchange', 'state'],
            'selectHosts': ['hostid', 'name'],
            'monitored': True,
            'active': True,
            'only_true': True,
            'sortfield': 'priority',
            'sortorder': 'DESC',
            'limit': limit,
        })

    def get_host_metrics(self, host_id: str) -> list[dict]:
        """Return key metric items for a single host."""
        return self.call('item.get', {
            'output': ['itemid', 'name', 'key_', 'lastvalue', 'units',
                        'lastclock', 'state', 'status'],
            'hostids': host_id,
            'search': {
                'key_': [
                    'system.cpu.util',
                    'vm.memory.utilization',
                    'vfs.fs.size',
                    'net.if',
                    'system.uptime',
                    'agent.ping',
                    'icmpping',
                ],
            },
            'searchByAny': True,
            'sortfield': 'name',
            'limit': 50,
        })

    def get_dashboard_summary(self) -> dict:
        """Build an aggregated overview for the dashboard KPI cards."""
        hosts = self.call('host.get', {
            'output': ['hostid', 'status'],
            'monitored_hosts': True,
            'countOutput': False,
        })
        total_hosts = len(hosts)
        available_hosts = sum(1 for h in hosts if str(h.get('status')) == '0')

        problems = self.call('problem.get', {
            'output': ['severity'],
            'recent': True,
        })
        severity_map = {
            '5': 'disaster',
            '4': 'high',
            '3': 'average',
            '2': 'warning',
            '1': 'information',
            '0': 'not_classified',
        }
        severity_counts: dict[str, int] = {v: 0 for v in severity_map.values()}
        for p in problems:
            label = severity_map.get(str(p.get('severity', '0')), 'not_classified')
            severity_counts[label] += 1

        triggers = self.call('trigger.get', {
            'output': ['triggerid'],
            'monitored': True,
            'active': True,
            'only_true': True,
            'countOutput': True,
        })

        return {
            'total_hosts': total_hosts,
            'available_hosts': available_hosts,
            'unavailable_hosts': total_hosts - available_hosts,
            'total_problems': len(problems),
            'problems_by_severity': severity_counts,
            'active_triggers': int(triggers) if isinstance(triggers, (int, str)) else 0,
        }
