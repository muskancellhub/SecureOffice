"""Discounted / featured catalog family (POTS-in-a-Box launch bundle).

Seeds a small set of promoted catalog entries that surface FIRST in the
storefront (``attributes.featured = True`` → pinned to the top by
``CatalogService.list_items`` and the catalog UI):

  * Multiline            — standalone per-line service ($20/line). The catalog
                           card shows a line-count dropdown and multiplies $20 x N.
  * POTS in a Box        — $95 device sold as a CONFIGURABLE BUNDLE: optional
                           Multiline lines + SIM + the two managed services,
                           configured together in the BundleConfigurator.
  * POTS Managed Service — $2.50 / mo managed service (standalone + in bundle).
  * Multiline Movius MS  — $1.00 / mo managed service (standalone + in bundle).
  * SIM Card             — $30 one-time SIM (system flat-price convention).
  * SMB Office Bundle     — $249 fixed bundle: network device + AP + AI device +
                           Security AI (the home-page "SMB" plan card).
  * Mobility             — Multiline + BYOD phone + optional Movius MS (the
                           home-page "Mobility" plan card).

The three home-page plan cards are POTS in a Box, SMB Office Bundle, and Mobility.

(The earlier $0 Phone placeholder is retired — handsets come from PAPI.)

Every price is FINAL: each primary component carries ``flat_price`` so the
pricing engine applies NO margin and the configured amount displays exactly.
Rich marketing copy for the two hero items lives in ``attributes.detail_sections``
/ ``attributes.services_table`` and is rendered on the product detail page.

Idempotent: re-running upserts by sku / (product_id, component_type,
vendor_component_sku). Commercial fields (cost) are written on first create only
so later admin edits survive a restart, mirroring ``mix_seed``.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models.product import (
    ComponentType,
    ComponentUom,
    FinancialModel,
    Product,
    ProductComponent,
)

DISC_VENDOR = 'CellhubMS'
_SOURCE = {'source_type': 'seed', 'source_name': 'discounted_seed'}


# ── rich detail copy (rendered on the product detail page) ───────────────────
MULTILINE_DETAILS = {
    'services_table': {
        'columns': ['Service', 'Description', 'Typical Use Case'],
        'rows': [
            ['Business Voice', 'Dedicated business number', 'Sales, support, executives'],
            ['Business SMS', 'Secure business texting', 'Customer communication'],
            ['MMS', 'Images and attachments', 'Field service, healthcare'],
            ['Voicemail', 'Separate business voicemail', 'BYOD deployments'],
            ['Call Recording', 'Compliance recording', 'Finance, healthcare'],
            ['SMS Archiving', 'Regulatory compliance', 'Banking, insurance'],
            ['WhatsApp Integration', 'Business WhatsApp with capture', 'International customer engagement'],
            ['Microsoft Teams Integration', 'Mobile identity within Teams', 'Hybrid workforce'],
            ['CRM Integration', 'Logging into CRM systems', 'Salesforce, customer support'],
            ['Analytics', 'Call, SMS, usage reporting', 'Operations management'],
            ['Administration Portal', 'User and number management', 'Enterprise IT'],
        ],
    },
    'detail_sections': [
        {
            'heading': 'BYOD (Bring Your Own Device)',
            'items': [
                'Personal phone remains private',
                'Business receives its own number',
                'No second handset required',
                'No physical SIM swap',
                'Ideal for: sales teams, executives, healthcare workers, retail managers',
            ],
        },
        {
            'heading': 'Secure Communications',
            'items': [
                'Voice, SMS, MMS',
                'WhatsApp and Microsoft Teams messaging',
                'Enterprise security and audit capabilities',
            ],
        },
        {
            'heading': 'Compliance',
            'items': [
                'Built for regulated industries: SEC, FINRA, HIPAA, GDPR',
                'Automatic recording and message capture',
                'Audit trail and eDiscovery',
                'Archiving integration and internal retention policies',
            ],
        },
    ],
}

POTS_DETAILS = {
    'detail_sections': [
        {
            'heading': 'Five Capabilities, One Appliance',
            'items': [
                'Connectivity — T-Mobile 5G + T-Priority support',
                'Power Protection — integrated battery backup for power-failure continuity',
                'Analog Communications — multi-port analog for life-safety & emergency lines',
                'Cloud Management — real-time monitoring, remote provisioning & diagnostics',
                'Managed Services — 24x7 monitoring, incident & lifecycle management',
            ],
        },
        {
            'heading': 'Supported Critical Applications',
            'items': [
                'Life Safety — fire alarm, elevator emergency phones, area-of-refuge, call stations',
                'Security — alarm panels, access control, gate entry',
                'Healthcare — nurse call, medical alert, fax communications',
                'Facilities — building management, intercom, environmental monitoring',
            ],
        },
        {
            'heading': 'Cloud Command Center',
            'items': [
                'Monitor — device status, battery health, signal strength, alarm conditions',
                'Control — configuration, provisioning, firmware, policy administration',
                'Analyze — historical performance, compliance reports, SLA & asset lifecycle',
            ],
        },
        {
            'heading': 'Compliance, Resiliency & Continuity',
            'items': [
                'Business continuity with failover and battery backup',
                'Proactive 24x7 NOC incident management',
                'Audit-ready compliance evidence, generated automatically',
                'T-Priority network-level resiliency on T-Mobile 5G',
            ],
        },
    ],
}


def _upsert_product(db, *, sku, name, technology, item_type, description, attributes) -> Product:
    prod = db.scalar(select(Product).where(Product.sku == sku))
    created = prod is None
    if created:
        prod = Product(sku=sku)
        db.add(prod)
    prod.vendor = DISC_VENDOR
    prod.technology = technology
    prod.vendor_sku = sku
    prod.name = name
    prod.description = description
    prod.default_financial_model = FinancialModel.BOTH
    if created:
        prod.margin_pct = None  # inherit (Phase 7 D2) — flat components ignore it anyway
        prod.is_active = True
    prod.attributes = {
        **(prod.attributes or {}),
        **attributes,
        'item_type': item_type,
        'featured': True,
        'discounted': True,
        'badge': attributes.get('badge', 'Discounted'),
        'availability': 'in_stock',
        'sellable': True,
        **_SOURCE,
    }
    db.flush()
    return prod


def _upsert_component(db, product_id, *, component_type, label, vendor_sku, cost,
                      uom, billing, interval, attributes, is_required=True,
                      is_active=True) -> ProductComponent:
    comp = db.scalar(
        select(ProductComponent).where(
            ProductComponent.product_id == product_id,
            ProductComponent.component_type == component_type,
            ProductComponent.vendor_component_sku == vendor_sku,
        )
    )
    created = comp is None
    if created:
        comp = ProductComponent(
            product_id=product_id, component_type=component_type, vendor_component_sku=vendor_sku
        )
        db.add(comp)
    comp.financial_model = FinancialModel.BOTH
    comp.label = label
    comp.uom = uom
    comp.billing = billing
    comp.interval = interval
    comp.is_required = is_required
    comp.attributes = attributes or {}
    if created:
        comp.vendor_cost = Decimal(str(cost))
        comp.is_active = is_active
    db.flush()
    return comp


def _deactivate_product(db, sku: str) -> int:
    """Retire a previously-seeded product (idempotent). Used to drop the Phone
    placeholder now that handsets come from the PAPI catalog."""
    prod = db.scalar(select(Product).where(Product.sku == sku))
    if prod is None or not prod.is_active:
        return 0
    prod.is_active = False
    for comp in prod.components:
        comp.is_active = False
    db.flush()
    return 1


def seed_discounted_items(db) -> dict:
    """Idempotently seed the featured/discounted catalog family. Safe on every
    startup. Returns a {'products', 'components'} summary."""
    products = 0
    components = 0

    # 1) Multiline — per-line service; the card dropdown multiplies $20 x N.
    p = _upsert_product(
        db, sku='DISC-MULTILINE', name='Multiline',
        technology='Multiline', item_type='DEVICE',
        description='Enterprise mobile identity and secure business communications — '
                    'BYOD voice, SMS/MMS, compliance and integrations. $20 per line.',
        attributes={
            'category': 'multiline', 'product_type': 'multiline',
            'is_multiline': True, 'per_line_price': 20, 'min_lines': 1, 'max_lines': 10,
            **MULTILINE_DETAILS,
        },
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.LINE_CHARGE, label='Line',
        vendor_sku='DISC-MULTILINE-LINE', cost='20.00', uom=ComponentUom.PER_LINE,
        billing='RECURRING', interval='MONTH', attributes={'flat_price': True},
    )
    products += 1
    components += 1

    # 2) POTS in a Box — a CONFIGURABLE BUNDLE: $95 device (required) plus
    #    optional Multiline lines, SIM, and the two managed services. Opens the
    #    BundleConfigurator (the product carries >1 component). Capacity caps the
    #    line/SIM counts exactly like the MIX 90X1.
    p = _upsert_product(
        db, sku='DISC-POTS-IN-A-BOX', name='POTS in a Box',
        technology='POTS', item_type='DEVICE',
        description='Managed life-safety and emergency communications — transform legacy '
                    'analog into a cloud-managed critical infrastructure service over '
                    'T-Mobile 5G and T-Priority. Configure your lines, SIM and managed '
                    'services below.',
        attributes={
            'category': 'router', 'product_type': 'router',
            'capacity': {'fxs_port': 8, 'max_sims': 2},
            **POTS_DETAILS,
        },
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.DEVICE, label='POTS in a Box (device)',
        vendor_sku='DISC-POTS-IN-A-BOX', cost='95.00', uom=ComponentUom.PER_DEVICE,
        billing='ONE_TIME', interval=None, attributes={'flat_price': True},
        is_required=True,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.LINE_CHARGE, label='Multiline (line)',
        vendor_sku='DISC-POTS-LINE', cost='20.00', uom=ComponentUom.PER_LINE,
        billing='RECURRING', interval='MONTH',
        attributes={'flat_price': True, 'consumes': {'fxs_port': 1}, 'requires_component_type': 'DEVICE'},
        is_required=False,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.SIM, label='SIM Card',
        vendor_sku='DISC-POTS-SIM', cost='30.00', uom=ComponentUom.PER_DEVICE,
        billing='ONE_TIME', interval=None,
        attributes={'flat_price': True, 'consumes': {'max_sims': 1}},
        is_required=False,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.MANAGED_SERVICE, label='POTS Managed Service',
        vendor_sku='DISC-POTS-BUNDLE-MS', cost='2.50', uom=ComponentUom.PER_DEVICE,
        billing='RECURRING', interval='MONTH', attributes={'flat_price': True},
        is_required=False,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.MANAGED_SERVICE, label='Multiline Movius MS',
        vendor_sku='DISC-POTS-BUNDLE-MOVIUS', cost='1.00', uom=ComponentUom.PER_DEVICE,
        billing='RECURRING', interval='MONTH', attributes={'flat_price': True},
        is_required=False,
    )
    products += 1
    components += 5

    # 3) POTS Managed Service — $2.50 / mo.
    p = _upsert_product(
        db, sku='DISC-POTS-MS', name='POTS Managed Service',
        technology='Managed Service', item_type='SERVICE',
        description='Managed monitoring, incident response and lifecycle support for your '
                    'POTS-in-a-Box lines.',
        attributes={
            'category': 'managed_service', 'product_type': 'managed_service',
            'service_kind': 'pots_managed', 'pricing_basis': 'PER_DEVICE',
        },
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.MANAGED_SERVICE, label='POTS Managed Service',
        vendor_sku='DISC-POTS-MS', cost='2.50', uom=ComponentUom.PER_DEVICE,
        billing='RECURRING', interval='MONTH', attributes={'flat_price': True},
    )
    products += 1
    components += 1

    # 4) Multiline Movius MS — $1.00 / mo.
    p = _upsert_product(
        db, sku='DISC-MOVIUS-MS', name='Multiline Movius MS',
        technology='Managed Service', item_type='SERVICE',
        description='Movius-managed multiline service — BYOD identity, compliance capture '
                    'and analytics.',
        attributes={
            'category': 'managed_service', 'product_type': 'managed_service',
            'service_kind': 'movius_managed', 'pricing_basis': 'PER_DEVICE',
        },
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.MANAGED_SERVICE, label='Multiline Movius MS',
        vendor_sku='DISC-MOVIUS-MS', cost='1.00', uom=ComponentUom.PER_DEVICE,
        billing='RECURRING', interval='MONTH', attributes={'flat_price': True},
    )
    products += 1
    components += 1

    # Phone placeholder is retired — handsets come from the PAPI catalog.
    _deactivate_product(db, 'DISC-PHONE')

    # 5) SIM Card — $30 one-time (system flat-price convention).
    p = _upsert_product(
        db, sku='DISC-SIM', name='SIM Card',
        technology='SIM', item_type='DEVICE',
        description='Carrier SIM card for cellular connectivity.',
        attributes={'category': 'sim', 'product_type': 'sim'},
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.SIM, label='SIM Card',
        vendor_sku='DISC-SIM', cost='30.00', uom=ComponentUom.PER_DEVICE,
        billing='ONE_TIME', interval=None, attributes={'flat_price': True},
    )
    products += 1
    components += 1

    # 6) SMB — $249 small-office bundle: network device + AP + AI device +
    #    Security AI. All required & flat, so the headline is exactly $249.
    p = _upsert_product(
        db, sku='DISC-SMB', name='SMB Office Bundle',
        technology='SMB', item_type='DEVICE',
        description='Everything a small office needs in one bundle — managed network, '
                    'Wi-Fi access point, an AI edge device and our Security AI small offer.',
        attributes={
            'category': 'smb', 'product_type': 'smb',
            'detail_sections': [{
                'heading': "What's included",
                'items': [
                    'SMB network device (managed gateway)',
                    'Wi-Fi Access Point (AP) device',
                    'AI edge device',
                    'Security AI — small office offer',
                ],
            }],
        },
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.DEVICE, label='SMB Network Device',
        vendor_sku='DISC-SMB-NET', cost='99.00', uom=ComponentUom.PER_DEVICE,
        billing='ONE_TIME', interval=None, attributes={'flat_price': True}, is_required=True,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.ACCESSORY, label='Wi-Fi Access Point (AP)',
        vendor_sku='DISC-SMB-AP', cost='60.00', uom=ComponentUom.PER_DEVICE,
        billing='ONE_TIME', interval=None, attributes={'flat_price': True}, is_required=True,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.ACCESSORY, label='AI Edge Device',
        vendor_sku='DISC-SMB-AI', cost='50.00', uom=ComponentUom.PER_DEVICE,
        billing='ONE_TIME', interval=None, attributes={'flat_price': True}, is_required=True,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.LICENSE, label='Security AI (small offer)',
        vendor_sku='DISC-SMB-SECAI', cost='40.00', uom=ComponentUom.PER_DEVICE,
        billing='ONE_TIME', interval=None, attributes={'flat_price': True}, is_required=True,
    )
    products += 1
    components += 4

    # 7) Mobility — "Multiline with phone". Required Multiline line ($20/mo);
    #    optional BYOD phone and the Movius managed service.
    p = _upsert_product(
        db, sku='DISC-MOBILITY', name='Mobility — Multiline with Phone',
        technology='Mobility', item_type='DEVICE',
        description='Business mobile identity — a dedicated Multiline business number on '
                    'your phone (BYOD), with optional Movius managed service.',
        attributes={
            'category': 'mobility', 'product_type': 'mobility',
            'detail_sections': [{
                'heading': "What's included",
                'items': [
                    'Multiline business number ($20 / line / mo)',
                    'BYOD — keep your personal phone private',
                    'Voice, SMS/MMS and Teams/WhatsApp',
                    'Optional Movius managed service',
                ],
            }],
        },
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.LINE_CHARGE, label='Multiline (line)',
        vendor_sku='DISC-MOBILITY-LINE', cost='20.00', uom=ComponentUom.PER_LINE,
        billing='RECURRING', interval='MONTH', attributes={'flat_price': True}, is_required=True,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.DEVICE, label='Phone — BYOD (bring your own)',
        vendor_sku='DISC-MOBILITY-PHONE', cost='0.00', uom=ComponentUom.PER_DEVICE,
        billing='ONE_TIME', interval=None, attributes={'flat_price': True, 'byod': True},
        is_required=False,
    )
    _upsert_component(
        db, p.id, component_type=ComponentType.MANAGED_SERVICE, label='Multiline Movius MS',
        vendor_sku='DISC-MOBILITY-MOVIUS', cost='1.00', uom=ComponentUom.PER_DEVICE,
        billing='RECURRING', interval='MONTH', attributes={'flat_price': True}, is_required=False,
    )
    products += 1
    components += 3

    db.commit()
    return {'products': products, 'components': components}
