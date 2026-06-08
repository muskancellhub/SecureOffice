"""MIX Networks catalog seed (Secure Office pricing engine, Phase 1).

Source of truth: ``MIX Networks Reseller Master Services Agreement.docx`` (Annex
pricing tables), verified 2026-06-04. Writes to the component model
(products / product_components) introduced in Phase 1 — NOT the legacy
catalog_items table. Idempotent: re-running upserts by sku /
(product_id, component_type, vendor_component_sku).

Pricing math is NOT applied here — this only stores cost / MSRP / margin /
leasing inputs and capacity metadata. The §3 worked example (660 / 19.78 /
82.88) is reproduced by the Phase 2 ComponentPricingService.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.core.tenancy import CELLHUB_MASTER_TENANT_ID
from app.models.financing import FinancingTerms
from app.models.product import ComponentType, ComponentUom, FinancialModel, Product, ProductComponent

MIX_VENDOR = 'MIX Networks'
DEFAULT_MARGIN = Decimal('0.20')   # manager's worked example
DEFAULT_LEASING = Decimal('0.05')  # per-SKU 'Leasing %ge' column

# Vendor-level commercial terms — notes only, NOT per-quote math (spec §10).
# The 100-line minimum is an ACCOUNT-level aggregate, not a per-assembly rule.
MIX_VENDOR_TERMS = {
    'wholesale_revenue_share': [
        {'min': 1, 'max': 499999, 'pct': 0.080},
        {'min': 500000, 'max': 999999, 'pct': 0.075},
        {'min': 1000000, 'max': None, 'pct': 0.070},
    ],
    'platform_branding_fee': 1500.00,
    'platform_fee_waived_if_trained_within_days': 60,
    'min_activated_lines_after_ramp': 100,
    'ramp_months': 6,
    'e911_unregistered_did_penalty_per_call': 150.00,
    # MIX's own financed hardware price (with credit approval) — different
    # mechanism from our cost-plus-annuity; informational only.
    'mix_financed_hardware_price': {'90X1': 591.00, '90X2': 303.00},
}


def _cap(fxs, lan, wan=1, sims=2):
    return {'fxs_port': fxs, 'lan_port': lan, 'wan_port': wan, 'max_sims': sims}


# ── Device products (DEVICE + MAINTENANCE/Cloud Controller components) ──
DEVICE_PRODUCTS = [
    {
        'sku': '90X1', 'vendor_sku': 'PROD7901', 'technology': 'POTS / Cellular Router',
        'name': 'POTS-in-a-Box 90X1 — 4G/5G LTE multi-carrier router (1 WAN/2 LAN, 8 FXS)',
        'description': 'POTS IN A BOX 4G/5G LTE multi-carrier router. 1 WAN/2 LAN, 8 FXS ports for '
                       'Voice/FAX/Alarm/Analog. Up to 24h standby battery.',
        'capacity': _cap(8, 2), 'sellable': True,
        'device_cost': '550.00', 'device_msrp': '675.00',
        'maint_cost': '7.75', 'maint_sku': 'SERV2158',
    },
    {
        'sku': '90X2', 'vendor_sku': 'PROD2279', 'technology': 'POTS / Cellular Router',
        'name': 'POTS-in-a-Box 90X2 — 4G/LTE multi-carrier router (1 WAN/4 LAN, 8 FXS)',
        'description': 'POTS IN A BOX 4G/LTE multi-carrier router. 1 WAN/4 LAN, 8 FXS ports for '
                       'Voice/FAX/Alarm/Analog. Up to 24h standby battery.',
        'capacity': _cap(8, 4), 'sellable': True,
        'device_cost': '280.00', 'device_msrp': '365.00',
        'maint_cost': '5.75', 'maint_sku': 'SERV2290',
    },
    {
        'sku': '90X2-NFR', 'vendor_sku': 'PROD2279-NFR', 'technology': 'POTS / Lab',
        'name': 'NFR POTS-in-a-Box 90X2 (lab/training, not for resale)',
        'description': 'NFR POTS IN A BOX 4G/LTE multi-carrier router. Testing/lab/training use only.',
        'capacity': _cap(8, 4), 'sellable': False,
        'device_cost': '240.00', 'device_msrp': None,
        'maint_cost': '5.75', 'maint_sku': 'SERV2290-NFR',
    },
]

# ── Shared add-on components, attached to each sellable device ──
# (type, label, vendor_sku, cost, uom, billing, interval, required, active, attributes)
SHARED_COMPONENTS = [
    # Voice / specialty lines (consume an FXS port — see capacity model §5).
    (ComponentType.LINE_CHARGE, 'PIAB Voice Line (RJ-11)', 'SERV1970', '11.50',
     ComponentUom.PER_LINE, 'RECURRING', 'MONTH', False, True,
     {'consumes': {'fxs_port': 1}, 'requires_component_type': 'DEVICE', 'msrp': 34.95}),
    (ComponentType.LINE_CHARGE, 'PIAB Specialty Line (Fax/Alarm/Modem)', 'SERV1969', '15.50',
     ComponentUom.PER_LINE, 'RECURRING', 'MONTH', False, True,
     {'consumes': {'fxs_port': 1}, 'requires_component_type': 'DEVICE', 'msrp': 49.95}),
    (ComponentType.LINE_CHARGE, 'Hosted PBX Seat', 'SERV075', '5.50',
     ComponentUom.PER_SEAT, 'RECURRING', 'MONTH', False, True, {'msrp': 19.95}),
    (ComponentType.LINE_CHARGE, 'Non-Continental DID add-on (AK/HI/PR)', 'SERV1986', '3.50',
     ComponentUom.PER_LINE, 'RECURRING', 'MONTH', False, True,
     {'nrc': 3.50, 'requires_component_type': 'DEVICE'}),
    # SIM — sourced from PAPI, flat $40 FINAL price, no margin (engine special-case §6).
    # Billed ONE-TIME (a SIM card is bought once) per product-owner decision 2026-06-04,
    # overriding §3's worked example which folded $40 into the monthly total.
    (ComponentType.SIM, 'Carrier SIM (PAPI)', 'PAPI-SIM', '40.00',
     ComponentUom.PER_DEVICE, 'ONE_TIME', None, False, True,
     {'consumes': {'max_sims': 1}, 'flat_price': True, 'source': 'PAPI'}),
    (ComponentType.BACKUP_SIM, 'Backup Carrier SIM (PAPI)', 'PAPI-SIM-BACKUP', '40.00',
     ComponentUom.PER_DEVICE, 'ONE_TIME', None, False, False,
     {'consumes': {'max_sims': 1}, 'flat_price': True, 'source': 'PAPI'}),
    # Managed service — per-SKU price (admin-set in /shop/services later).
    (ComponentType.MANAGED_SERVICE, 'Managed Service', 'MIX-MS', '15.50',
     ComponentUom.PER_DEVICE, 'RECURRING', 'MONTH', False, True, {}),
    # Install / professional services (one-time).
    (ComponentType.INSTALLATION, 'Staging/Kitting/Provisioning', 'SERV1987', '40.00',
     ComponentUom.PER_DEVICE, 'ONE_TIME', None, False, True, {}),
    (ComponentType.PROFESSIONAL_SERVICES, 'On-site Installation', 'SERV1817', '150.00',
     ComponentUom.PER_HOUR, 'ONE_TIME', None, False, True, {'min_hours': 2}),
    (ComponentType.PROFESSIONAL_SERVICES, 'Remote Install Assistance', 'SERV069', '125.00',
     ComponentUom.PER_HOUR, 'ONE_TIME', None, False, True, {}),
    (ComponentType.PROFESSIONAL_SERVICES, 'Remote Training/Support', 'SERV049', '200.00',
     ComponentUom.PER_HOUR, 'ONE_TIME', None, False, True, {'setup_fee': 500}),
    # Accessories (CAPEX one-time, optional).
    (ComponentType.ACCESSORY, 'Power Inverter', 'PROD7933', '30.00',
     ComponentUom.PER_DEVICE, 'ONE_TIME', None, False, True, {}),
    (ComponentType.ACCESSORY, 'Replacement Power Supply', 'PROD7643', '22.00',
     ComponentUom.PER_DEVICE, 'ONE_TIME', None, False, True, {}),
    (ComponentType.ACCESSORY, 'Replacement Battery', 'PROD7956', '106.25',
     ComponentUom.PER_DEVICE, 'ONE_TIME', None, False, True, {}),
    # Ancillary licenses/services — loaded INACTIVE by default; activate as offered.
    (ComponentType.LICENSE, '911 Services', 'SERV052', '0.59',
     ComponentUom.PER_DID, 'RECURRING', 'MONTH', False, False, {}),
    (ComponentType.LICENSE, 'Additional USA/Canada DID', 'SERV100', '0.20',
     ComponentUom.PER_DID, 'RECURRING', 'MONTH', False, False, {'nrc': 0.50}),
    (ComponentType.LICENSE, 'Caller ID (Inbound)', 'SERV013', '2.00',
     ComponentUom.PER_DID, 'RECURRING', 'MONTH', False, False, {}),
    (ComponentType.LICENSE, 'CNAM Registration/Storage', 'SERV1990', '2.00',
     ComponentUom.PER_DID, 'ONE_TIME', None, False, False, {'is_nrc': True}),
    (ComponentType.MANAGED_SERVICE, 'Call Recording', 'SERV077', '1.00',
     ComponentUom.PER_SEAT, 'RECURRING', 'MONTH', False, False, {}),
    (ComponentType.LICENSE, 'Toll-Free Service', 'SERV027', '1.50',
     ComponentUom.PER_DID, 'RECURRING', 'MONTH', False, False, {}),
]


def _upsert_product(db, spec) -> Product:
    prod = db.scalar(select(Product).where(Product.sku == spec['sku']))
    if prod is None:
        prod = Product(sku=spec['sku'])
        db.add(prod)
    prod.vendor = MIX_VENDOR
    prod.technology = spec['technology']
    prod.vendor_sku = spec['vendor_sku']
    prod.name = spec['name']
    prod.description = spec['description']
    prod.default_financial_model = FinancialModel.BOTH
    prod.margin_pct = DEFAULT_MARGIN
    prod.leasing_pct = DEFAULT_LEASING
    prod.is_active = True
    prod.attributes = {'capacity': spec['capacity'], 'vendor_terms': MIX_VENDOR_TERMS}
    db.flush()
    return prod


def _upsert_component(db, product_id, *, component_type, label, vendor_sku, cost, uom,
                      billing, interval, required, active, attributes, msrp=None,
                      financial_model=FinancialModel.BOTH):
    comp = db.scalar(
        select(ProductComponent).where(
            ProductComponent.product_id == product_id,
            ProductComponent.component_type == component_type,
            ProductComponent.vendor_component_sku == vendor_sku,
        )
    )
    if comp is None:
        comp = ProductComponent(
            product_id=product_id, component_type=component_type, vendor_component_sku=vendor_sku
        )
        db.add(comp)
    comp.financial_model = financial_model
    comp.label = label
    comp.vendor_cost = Decimal(cost)
    comp.msrp = Decimal(msrp) if msrp is not None else None
    comp.uom = uom
    comp.billing = billing
    comp.interval = interval
    comp.is_required = required
    comp.is_active = active
    comp.attributes = attributes or {}
    db.flush()
    return comp


def seed_mix_products(db) -> dict:
    """Idempotently seed MIX products/components + the default financing term.

    Returns a summary dict: {'products': N, 'components': M, 'financing_terms': K}.
    """
    products = []
    component_count = 0
    for spec in DEVICE_PRODUCTS:
        prod = _upsert_product(db, spec)
        products.append(prod)
        # Required DEVICE component.
        _upsert_component(
            db, prod.id, component_type=ComponentType.DEVICE,
            label=f'{spec["name"]} (device)', vendor_sku=spec['vendor_sku'],
            cost=spec['device_cost'], uom=ComponentUom.PER_DEVICE, billing='ONE_TIME',
            interval=None, required=True, active=True, attributes={},
            msrp=spec['device_msrp'], financial_model=FinancialModel.BOTH,
        )
        component_count += 1
        # Required MAINTENANCE / Cloud Controller component.
        _upsert_component(
            db, prod.id, component_type=ComponentType.MAINTENANCE,
            label='Cloud Controller / Maintenance', vendor_sku=spec['maint_sku'],
            cost=spec['maint_cost'], uom=ComponentUom.PER_DEVICE, billing='RECURRING',
            interval='MONTH', required=True, active=True, attributes={},
        )
        component_count += 1
        # Shared add-ons only on sellable devices (skip the NFR lab unit).
        if spec['sellable']:
            for (ctype, label, vsku, cost, uom, billing, interval, required, active, attrs) in SHARED_COMPONENTS:
                attrs_copy = dict(attrs)  # never mutate the module-level constant
                msrp = attrs_copy.pop('msrp', None)
                _upsert_component(
                    db, prod.id, component_type=ctype, label=label, vendor_sku=vsku,
                    cost=cost, uom=uom, billing=billing, interval=interval,
                    required=required, active=active, attributes=attrs_copy, msrp=msrp,
                )
                component_count += 1

    # Default financing term (36 mo / 5%) — reproduces the §3 lease MRC of $19.78.
    # Owned by the CellHub master tenant (multi-tenant Phase 1); other tenants get
    # their own copy via clone-on-onboard. Dedup by (tenant, name) — the unique key
    # — not by is_default, since a prior row may have been demoted and re-inserting
    # the same name would violate uq_financing_tenant_name.
    existing = db.scalar(
        select(FinancingTerms).where(
            FinancingTerms.tenant_id == CELLHUB_MASTER_TENANT_ID,
            FinancingTerms.name == 'Standard 36-mo',
        )
    )
    has_default = db.scalar(
        select(FinancingTerms).where(
            FinancingTerms.tenant_id == CELLHUB_MASTER_TENANT_ID,
            FinancingTerms.is_default.is_(True),
        )
    )
    if existing is None:
        # Claim default only if the master tenant has none yet (per-tenant index).
        db.add(FinancingTerms(
            tenant_id=CELLHUB_MASTER_TENANT_ID,
            name='Standard 36-mo', term_months=36, annual_rate_pct=Decimal('0.0500'),
            subscription_interval='MONTH', is_default=has_default is None, is_active=True,
        ))
    elif has_default is None:
        # The term exists but the tenant lost its default (e.g. legacy data) —
        # promote the canonical 36-mo term so pricing always has a default.
        existing.is_default = True

    db.commit()
    return {
        'products': len(products),
        'components': component_count,
        'financing_terms': 1,
    }
