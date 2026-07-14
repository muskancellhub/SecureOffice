"""Avalara AvaTax service — US sales-tax calculation over httpx.

Production-only (no sandbox account provisioned); estimate-only. Every call is a
non-committing SalesOrder transaction (docs/plans/AVALARA_TAX_PLAN.md) — nothing
is recorded on Avalara's side, so there is no filing liability.
``ALLOW_AVALARA_COMMIT`` is a hard guardrail: a committing SalesInvoice is sent
ONLY when both the caller asks for it AND the flag is true; while false (the only
supported mode today) we always send SalesOrder.

Auth is HTTP Basic (account_id:license_key). The base URL is derived from
AVALARA_ENVIRONMENT so an environment/key handoff is a config-only swap. We omit
companyCode and shipFrom → Avalara uses the account's single default company and
its console-configured origin address.

With no nexus configured Avalara legitimately returns ``totalTax = 0.0``; that is
a CORRECT result, not a failure. Callers verify the response *shape* (a resolved
transaction carrying ``totalTax``), never ``tax > 0``.
"""
import base64
import logging
from dataclasses import dataclass, field
from datetime import date

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


class AvalaraError(Exception):
    """Avalara returned a non-2xx response or was unreachable. Fail-closed: the
    caller treats this as 'tax could not be calculated' and blocks the charge
    rather than under-collecting."""

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


@dataclass
class TaxAddress:
    line1: str
    city: str
    region: str          # 2-letter US state code
    postal_code: str
    country: str = 'US'

    def to_avalara(self) -> dict:
        return {
            'line1': self.line1 or '',
            'city': self.city or '',
            'region': self.region or '',
            'postalCode': self.postal_code or '',
            'country': self.country or 'US',
        }


@dataclass
class TaxQuote:
    subtotal: float                       # dollars, pre-tax
    tax: float                            # dollars, sales tax
    total: float                          # dollars, subtotal + tax
    breakdown: list[dict] = field(default_factory=list)  # per-jurisdiction summary


class AvalaraService:
    ESTIMATE_TYPE = 'SalesOrder'          # non-committing
    COMMITTING_TYPE = 'SalesInvoice'      # gated by ALLOW_AVALARA_COMMIT

    @staticmethod
    def is_configured() -> bool:
        return bool(_settings.avalara_account_id and _settings.avalara_license_key)

    @staticmethod
    def _headers() -> dict:
        raw = f'{_settings.avalara_account_id}:{_settings.avalara_license_key}'.encode('utf-8')
        token = base64.b64encode(raw).decode('ascii')
        return {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Avalara-Client': 'SecureOffice2; 1.0; python; v2',
        }

    @staticmethod
    def _url(path: str) -> str:
        return f"{_settings.avalara_base_url.rstrip('/')}{path}"

    @classmethod
    def estimate_tax(
        cls,
        *,
        subtotal: float,
        ship_to: TaxAddress,
        customer_code: str,
        commit: bool = False,
        txn_date: date | None = None,
    ) -> TaxQuote:
        """Calculate US sales tax on ``subtotal`` dollars shipped to ``ship_to``.

        Non-committing by default. A committing transaction is sent only when
        ``commit`` is True AND ``ALLOW_AVALARA_COMMIT`` is set — otherwise it
        silently stays a SalesOrder (the guardrail). Raises ``AvalaraError`` on
        any transport/HTTP error so the caller can fail closed.
        """
        if subtotal <= 0:
            return TaxQuote(subtotal=subtotal, tax=0.0, total=subtotal)
        if not cls.is_configured():
            raise AvalaraError('Avalara is not configured (missing AVALARA_ACCOUNT_ID / AVALARA_LICENSE_KEY).')

        committing = bool(commit and _settings.allow_avalara_commit)
        body = {
            'type': cls.COMMITTING_TYPE if committing else cls.ESTIMATE_TYPE,
            'commit': committing,
            'date': (txn_date or date.today()).isoformat(),
            'customerCode': customer_code or 'GUEST',
            'addresses': {
                # shipFrom omitted → Avalara uses the default company's configured
                # origin address (set in the Avalara console).
                'shipTo': ship_to.to_avalara(),
            },
            'lines': [{
                'number': '1',
                'quantity': 1,
                'amount': round(float(subtotal), 2),
                'description': 'Order charge',
            }],
            # companyCode intentionally omitted → account's single default company.
        }

        try:
            resp = httpx.post(cls._url('/api/v2/transactions/create'),
                              headers=cls._headers(), json=body, timeout=15)
        except httpx.HTTPError as exc:
            logger.warning('Avalara request failed: %s', exc)
            raise AvalaraError(f'Avalara request failed: {exc}') from exc

        if resp.status_code >= 400:
            try:
                detail = (resp.json().get('error') or {}).get('message', '')
            except ValueError:
                detail = resp.text[:200]
            logger.warning('Avalara HTTP %s: %s', resp.status_code, detail)
            raise AvalaraError(f'Avalara error (HTTP {resp.status_code}): {detail}', resp.status_code)

        data = resp.json()
        # Shape check: a resolved transaction carries totalTax + a summary array.
        # This is how a legit $0 (no nexus) is distinguished from a silent failure.
        if 'totalTax' not in data:
            raise AvalaraError('Avalara returned an unexpected response (no totalTax).')

        tax = float(data.get('totalTax') or 0.0)
        return TaxQuote(
            subtotal=round(subtotal, 2),
            tax=round(tax, 2),
            total=round(subtotal + tax, 2),
            breakdown=data.get('summary') or [],
        )
