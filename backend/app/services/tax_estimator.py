"""Split-cadence sales-tax estimation (BUG-MS-TAX-001 / BUG-MS-TAX-002).

One-time and recurring (monthly) charges are taxed *separately* so the UI can
show a monthly-including-tax figure alongside the one-time total — the old code
lumped everything into one subtotal and taxed only the one-time hardware.

Rate source (product decision): Avalara jurisdiction by the customer's ship-to
address, ALL lines taxable. Avalara is production-only and returns $0 with no
nexus configured, and is unconfigured in dev — so for an *estimate* (not a
committed charge) we degrade gracefully to the caller's configured percentage
rather than failing closed. Every result records which source was used.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.services.avalara_service import AvalaraError, AvalaraService, TaxAddress

logger = logging.getLogger(__name__)


@dataclass
class CadenceTax:
    subtotal: float
    tax: float
    total: float
    source: str  # 'avalara' | 'configured' | 'none'


@dataclass
class SplitTaxResult:
    one_time: CadenceTax
    recurring: CadenceTax  # per-month
    breakdown: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            'one_time_subtotal': self.one_time.subtotal,
            'one_time_tax': self.one_time.tax,
            'one_time_total': self.one_time.total,
            'recurring_subtotal': self.recurring.subtotal,
            'recurring_tax': self.recurring.tax,
            'recurring_total': self.recurring.total,   # monthly incl. tax
            'tax_source': self.one_time.source if self.one_time.subtotal else self.recurring.source,
            'tax_breakdown': self.breakdown,
        }


def _estimate_one(
    subtotal: float,
    *,
    ship_to: TaxAddress | None,
    customer_code: str,
    fallback_rate_pct: float,
) -> tuple[CadenceTax, list[dict]]:
    """Tax a single cadence's subtotal. Avalara first (jurisdiction), then fall
    back to the configured percentage if Avalara is unavailable/unconfigured."""
    subtotal = round(float(subtotal or 0.0), 2)
    if subtotal <= 0:
        return CadenceTax(subtotal=0.0, tax=0.0, total=0.0, source='none'), []

    if ship_to is not None and AvalaraService.is_configured():
        try:
            quote = AvalaraService.estimate_tax(
                subtotal=subtotal, ship_to=ship_to, customer_code=customer_code or 'GUEST')
            return (
                CadenceTax(subtotal=quote.subtotal, tax=quote.tax, total=quote.total, source='avalara'),
                quote.breakdown,
            )
        except AvalaraError as exc:
            # Estimate must degrade, not block — log and fall through to the rate.
            logger.warning('Avalara estimate failed (%s); falling back to configured rate.', exc)

    rate = max(0.0, float(fallback_rate_pct or 0.0))
    tax = round(subtotal * (rate / 100.0), 2)
    return CadenceTax(subtotal=subtotal, tax=tax, total=round(subtotal + tax, 2),
                      source='configured' if rate > 0 else 'none'), []


def estimate_split_tax(
    *,
    one_time_subtotal: float,
    recurring_subtotal: float,
    ship_to: TaxAddress | None,
    customer_code: str,
    fallback_rate_pct: float,
) -> SplitTaxResult:
    """Compute one-time and monthly-recurring tax independently. Returns a
    SplitTaxResult carrying both cadences and the rate source used."""
    one_time, ot_bd = _estimate_one(
        one_time_subtotal, ship_to=ship_to, customer_code=customer_code, fallback_rate_pct=fallback_rate_pct)
    recurring, rc_bd = _estimate_one(
        recurring_subtotal, ship_to=ship_to, customer_code=customer_code, fallback_rate_pct=fallback_rate_pct)
    return SplitTaxResult(one_time=one_time, recurring=recurring, breakdown=(ot_bd or rc_bd))


def address_from_dict(addr: dict | None) -> TaxAddress | None:
    """Build a TaxAddress from an onboarding-style address dict, or None when it
    lacks the minimum fields Avalara needs (a state + ZIP)."""
    if not addr:
        return None
    region = (addr.get('state') or addr.get('region') or '').strip()
    postal = (addr.get('postal_code') or addr.get('zip') or '').strip()
    if not region or not postal:
        return None
    return TaxAddress(
        line1=(addr.get('line1') or '').strip(),
        city=(addr.get('city') or '').strip(),
        region=region,
        postal_code=postal,
        country=(addr.get('country') or 'US').strip() or 'US',
    )
