"""Square payments service — talks to the Square REST API over httpx.

Square's Web Payments flow: the
frontend tokenizes the card inside Square's iframe and posts us a one-time
``source_id`` (nonce); we charge it server-side with CreatePayment
(docs/SQUARE_MIGRATION_PLAN.md §3–§6). Sandbox host by default; production is a
config-only swap of SQUARE_API_BASE / SQUARE_ACCESS_TOKEN / SQUARE_LOCATION_ID.

No raw card data ever reaches this code — only the opaque nonce.
"""
import base64
import hashlib
import hmac
import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.order import Order
from app.models.quote import BillingType
from app.services.audit_logger import audit
from app.models.onboarding import TenantOnboarding
from app.services.avalara_service import AvalaraService, AvalaraError, TaxAddress

logger = logging.getLogger(__name__)

_settings = get_settings()

# Statuses Square returns for a successfully charged payment. APPROVED means the
# funds are authorized (auto-completes to COMPLETED for our autocomplete=true
# requests); COMPLETED means captured. Either is a "money moved" signal for us.
_PAID_STATUSES = {'APPROVED', 'COMPLETED'}


class SquareError(Exception):
    """A non-2xx response from the Square API. Carries the parsed error list so
    routes can surface a useful (non-sensitive) detail to the caller."""

    def __init__(self, status_code: int, errors: list[dict]):
        self.status_code = status_code
        self.errors = errors or []
        detail = '; '.join(
            f"{e.get('category', '')}/{e.get('code', '')}: {e.get('detail', '')}".strip('/ ')
            for e in self.errors
        ) or f'Square API error (HTTP {status_code})'
        super().__init__(detail)


class SquareService:
    def __init__(self, db: Session):
        self.db = db

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _headers() -> dict:
        return {
            'Authorization': f'Bearer {_settings.square_access_token}',
            'Square-Version': _settings.square_version,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    @staticmethod
    def _url(path: str) -> str:
        return f"{_settings.square_api_base.rstrip('/')}{path}"

    @staticmethod
    def _raise_for_errors(resp: httpx.Response) -> dict:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400:
            raise SquareError(resp.status_code, body.get('errors', []))
        return body

    @staticmethod
    def order_subtotal_cents(order: Order) -> int:
        """One-time, PRE-TAX charge for the order in cents.

        Only ONE_TIME lines are charged upfront. RECURRING lines are billed
        monthly by the invoicing engine — including them here would double-bill.
        """
        total = 0
        for line in order.lines:
            billing = getattr(line.billing_type, 'value', line.billing_type)
            if billing == BillingType.RECURRING.value:
                continue
            unit_amount = int(round(float(line.final_unit_price_snapshot) * 100))
            total += unit_amount * int(line.qty)
        return total

    def _ship_to_address(self, order: Order) -> TaxAddress | None:
        """Destination (tax jurisdiction) = the tenant's billing address, falling
        back to operations_address. None if no usable US address is on file."""
        row = self.db.get(TenantOnboarding, order.tenant_id)
        if not row:
            return None
        addr = row.billing_address or {}
        if not (addr.get('line1') or addr.get('postal_code')):
            addr = row.operations_address or {}
        if not (addr.get('postal_code') or addr.get('city')):
            return None
        return TaxAddress(
            line1=addr.get('line1', ''),
            city=addr.get('city', ''),
            region=addr.get('state', ''),
            postal_code=addr.get('postal_code', ''),
            country=addr.get('country') or 'US',
        )

    def order_charge_breakdown(self, order: Order) -> dict:
        """{subtotal, tax, total, breakdown} in dollars for the one-time charge.

        Tax is computed live from the tenant's own line prices (per-tenant
        pricing) + destination address. Fails CLOSED: propagates AvalaraError so
        the caller blocks the charge rather than under-collecting. When there's
        nothing to tax or Avalara isn't configured, returns subtotal only.
        """
        subtotal = self.order_subtotal_cents(order) / 100
        if subtotal <= 0 or not AvalaraService.is_configured():
            return {'subtotal': subtotal, 'tax': 0.0, 'total': subtotal, 'breakdown': []}

        ship_to = self._ship_to_address(order)
        if ship_to is None:
            raise AvalaraError('No billing/operations address on file for this tenant; cannot calculate tax.')

        quote = AvalaraService.estimate_tax(
            subtotal=subtotal,
            ship_to=ship_to,
            customer_code=str(order.tenant_id),  # per-tenant, by who is logged in
        )
        return {'subtotal': quote.subtotal, 'tax': quote.tax,
                'total': quote.total, 'breakdown': quote.breakdown}
    # ── payments ─────────────────────────────────────────────────────────────
    def create_payment(self, order: Order, source_id: str, idempotency_key: str,
                       amount_cents: int | None = None) -> dict:
        """Charge the card. ``amount_cents`` is the tax-inclusive total computed
        by the caller (route) via order_charge_breakdown; falls back to the
        pre-tax subtotal only if not supplied."""
        amount = amount_cents if amount_cents is not None else self.order_subtotal_cents(order)
        payload = {
            'source_id': source_id,
            'idempotency_key': idempotency_key,
            'amount_money': {'amount': amount, 'currency': 'USD'},
            'location_id': _settings.square_location_id,
            'reference_id': str(order.id),
            'note': f'Order {getattr(order, "public_id", "") or order.id}',
            'autocomplete': True,
        }
        resp = httpx.post(self._url('/v2/payments'), headers=self._headers(),
                          json=payload, timeout=30)
        body = self._raise_for_errors(resp)
        payment = body.get('payment', {})
        audit.log('square_payment_created',
                  checkout_tenant_id=str(order.tenant_id), order_id=str(order.id),
                  payment_id=payment.get('id'), payment_status=payment.get('status'),
                  amount_cents=amount)
        return payment

    def get_payment(self, payment_id: str) -> dict:
        resp = httpx.get(self._url(f'/v2/payments/{payment_id}'),
                         headers=self._headers(), timeout=30)
        body = self._raise_for_errors(resp)
        return body.get('payment', {})

    def get_order(self, square_order_id: str) -> dict:
        resp = httpx.get(self._url(f'/v2/orders/{square_order_id}'),
                         headers=self._headers(), timeout=30)
        body = self._raise_for_errors(resp)
        return body.get('order', {})

    # ── webhooks ─────────────────────────────────────────────────────────────
    @staticmethod
    def verify_webhook(body: bytes, signature: str, notification_url: str) -> bool:
        """Validate Square's HMAC-SHA256 webhook signature.

        Square computes base64(HMAC_SHA256(signature_key, notification_url + body))
        and sends it in the ``x-square-hmacsha256-signature`` header. We recompute
        and compare in constant time. Returns False on any mismatch / missing key.
        """
        key = _settings.square_webhook_signature_key
        if not key or not signature:
            return False
        mac = hmac.new(key.encode('utf-8'),
                       notification_url.encode('utf-8') + body,
                       hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode('utf-8')
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def is_paid_status(status: str | None) -> bool:
        return (status or '').upper() in _PAID_STATUSES
