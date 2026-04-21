"""RAG-based chatbot service for SecureOffice2 portal.

Retrieves relevant data from the database (devices, orders, quotes, designs,
assets, subscriptions, billing) and uses OpenAI to generate contextual answers.
"""

import json
import logging
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.catalog import CatalogItem, CatalogItemType
from app.models.order import Order, OrderLine
from app.models.quote import Quote, QuoteLine
from app.models.cart import Cart, CartLine
from app.models.lifecycle import (
    Asset, Contract, Subscription, Invoice, WorkflowInstance, WorkflowStep,
)
from app.models.network_design import NetworkDesign
from app.models.onboarding import TenantOnboarding

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Intent detection keywords – used to decide which DB tables to query
# ---------------------------------------------------------------------------
INTENT_KEYWORDS: dict[str, list[str]] = {
    'catalog': ['device', 'router', 'catalog', 'product', 'equipment', 'hardware',
                'switch', 'access point', 'firewall', 'sku', 'brand', 'vendor',
                'price', 'cost', 'cheap', 'expensive', 'available', 'buy', 'browse',
                'network', 'wifi', 'wireless', 'port', 'service', 'managed service',
                't-mobile', 'tmobile', 't mobile', 'papi', 'phone', 'phones',
                'tablet', 'tablets', 'laptop', 'laptops', 'hotspot', 'hotspots',
                'mobile', 'cellular', 'smartphone', 'iphone', 'samsung', 'galaxy',
                'android', 'sim', '5g', 'lte'],
    'cabling': ['cable', 'cabling', 'cat5', 'cat6', 'cat6e', 'wiring', 'wire',
                'ethernet', 'drop', 'patch', 'structured cabling', 'cable run',
                'cable length', 'cable cost', 'cable type'],
    'cart': ['cart', 'shopping', 'added', 'items in my cart', 'checkout'],
    'orders': ['order', 'purchase', 'delivery', 'ship', 'track', 'bought'],
    'quotes': ['quote', 'estimate', 'proposal', 'pricing', 'discount'],
    'designs': ['design', 'topology', 'network design', 'bom', 'bill of materials',
                'blueprint', 'architecture', 'wired', 'wireless', 'connectivity'],
    'assets': ['asset', 'deployed', 'installed', 'serial number', 'location',
               'provisioning', 'active device', 'retired'],
    'subscriptions': ['subscription', 'recurring', 'monthly', 'yearly', 'renew',
                      'cancel', 'pause'],
    'contracts': ['contract', 'sla', 'term', 'entitlement', 'agreement'],
    'billing': ['billing', 'invoice', 'payment', 'due', 'paid', 'amount owed'],
    'onboarding': ['onboarding', 'setup', 'company setup', 'tax', 'credit', 'duns'],
    'general': ['help', 'how', 'what', 'where', 'who', 'portal', 'navigate',
                'page', 'feature', 'support'],
}

# ---------------------------------------------------------------------------
# Guardrails — topics and patterns the chatbot must refuse
# ---------------------------------------------------------------------------
BLOCKED_TOPICS: list[str] = [
    # Off-topic / harmful
    'hack', 'exploit', 'vulnerability', 'bypass', 'jailbreak',
    'password crack', 'brute force', 'ddos', 'denial of service',
    # Personal / sensitive
    'social security', 'ssn', 'credit card number', 'bank account',
    'personal address', 'home address', 'date of birth',
    # Competitor intelligence
    'competitor pricing', 'competitor strategy',
    # Medical / legal advice
    'medical advice', 'legal advice', 'lawsuit', 'diagnosis',
]

GUARDRAIL_RESPONSE = (
    "I'm the SecureOffice2 portal assistant. I can help with network devices, "
    "cabling (CAT5/CAT6/CAT6e), orders, quotes, designs, billing, and portal navigation. "
    "I'm not able to help with that particular topic. "
    "Try asking about your devices, orders, or network designs!"
)

DIAGRAM_SEMANTICS_RESPONSE = (
    "Quick clarification for topology diagrams:\n"
    "• Diagram lines are connectivity relationships, not literal cable routing paths.\n"
    "• `Wired link` = local Ethernet dependency.\n"
    "• `Wireless link` = Wi-Fi relationship.\n"
    "• `Managed connection` = service/management overlay.\n"
    "For BOM cabling, we use typed CAT standards (CAT5/CAT6/CAT6e) and derive cost from office area."
)


def _check_guardrails(message: str) -> str | None:
    """Return a refusal message if the user query hits a blocked topic, else None."""
    msg_lower = message.lower()
    for blocked in BLOCKED_TOPICS:
        if blocked in msg_lower:
            return GUARDRAIL_RESPONSE
    # Block very short or empty messages
    stripped = message.strip()
    if len(stripped) < 2:
        return 'Please ask a question about the SecureOffice2 portal — devices, cabling, orders, designs, or billing.'
    return None


def _check_diagram_semantics_guardrail(message: str) -> str | None:
    msg_lower = message.lower()
    mentions_diagram = any(
        token in msg_lower
        for token in ('diagram', 'topology', 'network map', 'drawio', 'draw.io')
    )
    mentions_wire = any(
        token in msg_lower
        for token in ('wire', 'wires', 'wiring', 'cable', 'cables')
    )
    mentions_diagram_line_phrase = any(
        phrase in msg_lower
        for phrase in ('diagram lines', 'topology lines', 'lines in diagram', 'lines in topology')
    )
    if mentions_diagram and (mentions_wire or mentions_diagram_line_phrase):
        return DIAGRAM_SEMANTICS_RESPONSE
    return None


def _detect_intents(message: str) -> list[str]:
    """Return a ranked list of intent keys matching the user message."""
    msg_lower = message.lower()
    scores: dict[str, int] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in msg_lower)
        if score > 0:
            scores[intent] = score
    if not scores:
        scores['general'] = 1
        scores['catalog'] = 1  # default: assume device question
    return sorted(scores, key=scores.get, reverse=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Data retrieval helpers – each returns a text block for the LLM context
# ---------------------------------------------------------------------------

def _fmt_currency(val: float | None) -> str:
    if val is None:
        return 'N/A'
    return f'${val:,.2f}'


_TMOBILE_KEYWORDS = {'t-mobile', 'tmobile', 't mobile', 'papi'}
_CATEGORY_KEYWORDS = {
    'phone': ['phone', 'phones', 'smartphone', 'iphone', 'samsung', 'galaxy', 'android'],
    'tablet': ['tablet', 'tablets', 'ipad'],
    'laptop': ['laptop', 'laptops', 'notebook'],
    'hotspot': ['hotspot', 'hotspots', 'mifi', 'jetpack'],
}


def _is_tmobile_intent(msg_lower: str) -> bool:
    return any(kw in msg_lower for kw in _TMOBILE_KEYWORDS)


def _infer_device_category(msg_lower: str) -> str | None:
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            return cat
    return None


def _retrieve_catalog(db: Session, tenant_id: str, message: str) -> str:
    """Search catalog items relevant to the query."""
    msg_lower = message.lower()
    q = db.query(CatalogItem).filter(CatalogItem.is_active.is_(True))

    # Detect T-Mobile / PAPI intent — filter by source
    tmobile = _is_tmobile_intent(msg_lower)
    if tmobile:
        q = q.filter(CatalogItem.attributes['source_type'].astext == 'paapi')

    # Narrow by device category if mentioned
    cat_filter = _infer_device_category(msg_lower)
    if cat_filter:
        q = q.filter(CatalogItem.attributes['category'].astext == cat_filter)

    # Narrow by type if message suggests it
    if not tmobile and not cat_filter:
        if any(kw in msg_lower for kw in ['service', 'managed service', 'monitoring', 'backup']):
            q = q.filter(CatalogItem.type == CatalogItemType.SERVICE)
        elif any(kw in msg_lower for kw in ['device', 'router', 'switch', 'firewall', 'access point', 'hardware']):
            q = q.filter(CatalogItem.type == CatalogItemType.DEVICE)

    # Text search across name, vendor, sku, description (skip if already filtered by source/category)
    if not tmobile and not cat_filter:
        search_terms = [w for w in msg_lower.split() if len(w) > 2 and w not in (
            'the', 'and', 'for', 'how', 'much', 'does', 'what', 'are', 'can', 'you',
            'show', 'list', 'all', 'any', 'tell', 'about', 'with', 'which', 'have',
            'available', 'price', 'cost', 'device', 'devices', 'router', 'routers',
            'service', 'services', 'product', 'products',
        )]
        if search_terms:
            filters = []
            for term in search_terms[:5]:
                pattern = f'%{term}%'
                filters.append(CatalogItem.name.ilike(pattern))
                filters.append(CatalogItem.vendor.ilike(pattern))
                filters.append(CatalogItem.sku.ilike(pattern))
                filters.append(CatalogItem.description.ilike(pattern))
            q = q.filter(or_(*filters))

    items = q.order_by(CatalogItem.name).limit(25).all()

    if not items and not tmobile:
        # Fallback: return top items
        items = (
            db.query(CatalogItem)
            .filter(CatalogItem.is_active.is_(True))
            .order_by(CatalogItem.name)
            .limit(10)
            .all()
        )

    source_label = 'T-Mobile Device Catalog' if tmobile else 'CATALOG'
    lines = [f'[{source_label} — {len(items)} items found]']
    for it in items:
        attrs = it.attributes or {}
        ms_price = f' | MS: {_fmt_currency(float(it.managed_service_price))}/mo' if it.managed_service_price else ''
        detail_parts = []
        for key in ('brand', 'model', 'color', 'memory', 'os'):
            val = attrs.get(key)
            if val:
                detail_parts.append(f'{key}: {val}')
        detail_str = ', '.join(detail_parts[:5])
        lines.append(
            f'• {it.name} | SKU: {it.sku} | Vendor: {it.vendor or "N/A"} '
            f'| Type: {it.type.value} | Price: {_fmt_currency(float(it.price))} '
            f'| Billing: {it.billing_cycle.value} | Availability: {it.availability or "N/A"}'
            f'{ms_price}'
            + (f' | {detail_str}' if detail_str else '')
        )
    return '\n'.join(lines)


def _retrieve_cart(db: Session, tenant_id: str, _message: str) -> str:
    cart = db.query(Cart).filter(Cart.tenant_id == tenant_id).first()
    if not cart or not cart.lines:
        return '[CART] Your cart is currently empty.'
    lines_info = []
    for cl in cart.lines:
        lines_info.append(
            f'• {cl.item_name} (x{cl.quantity}) — {_fmt_currency(float(cl.unit_price))} each'
        )
    return (
        f'[CART — {len(cart.lines)} items]\n'
        + '\n'.join(lines_info)
        + f'\nOne-time subtotal: {_fmt_currency(float(cart.one_time_subtotal))}'
        f' | Monthly subtotal: {_fmt_currency(float(cart.monthly_subtotal))}'
    )


def _retrieve_orders(db: Session, tenant_id: str, _message: str) -> str:
    orders = (
        db.query(Order).filter(Order.tenant_id == tenant_id)
        .order_by(Order.created_at.desc()).limit(10).all()
    )
    if not orders:
        return '[ORDERS] No orders found.'
    lines = [f'[ORDERS — {len(orders)} most recent]']
    for o in orders:
        line_count = db.query(func.count(OrderLine.id)).filter(OrderLine.order_id == o.id).scalar()
        lines.append(
            f'• Order {str(o.id)[:8]}… | Status: {o.status.value} '
            f'| Items: {line_count} | Created: {o.created_at.strftime("%Y-%m-%d") if o.created_at else "N/A"}'
        )
    return '\n'.join(lines)


def _retrieve_quotes(db: Session, tenant_id: str, _message: str) -> str:
    quotes = (
        db.query(Quote).filter(Quote.tenant_id == tenant_id)
        .order_by(Quote.created_at.desc()).limit(10).all()
    )
    if not quotes:
        return '[QUOTES] No quotes found.'
    lines = [f'[QUOTES — {len(quotes)} most recent]']
    for q in quotes:
        lines.append(
            f'• Quote {str(q.id)[:8]}… | Status: {q.status.value} '
            f'| One-time: {_fmt_currency(float(q.one_time_total))} '
            f'| Monthly: {_fmt_currency(float(q.monthly_total))} '
            f'| Created: {q.created_at.strftime("%Y-%m-%d") if q.created_at else "N/A"}'
        )
    return '\n'.join(lines)


def _retrieve_designs(db: Session, tenant_id: str, _message: str) -> str:
    designs = (
        db.query(NetworkDesign).filter(NetworkDesign.tenant_id == tenant_id)
        .order_by(NetworkDesign.created_at.desc()).limit(10).all()
    )
    if not designs:
        return '[DESIGNS] No network designs found.'
    lines = [f'[DESIGNS — {len(designs)} most recent]']
    for d in designs:
        lines.append(
            f'• Design {str(d.id)[:8]}… | Name: {d.design_name or "Untitled"} '
            f'| Status: {d.status.value} '
            f'| Created: {d.created_at.strftime("%Y-%m-%d") if d.created_at else "N/A"}'
        )
    return '\n'.join(lines)


def _retrieve_assets(db: Session, tenant_id: str, _message: str) -> str:
    assets = (
        db.query(Asset).filter(Asset.tenant_id == tenant_id)
        .order_by(Asset.created_at.desc()).limit(15).all()
    )
    if not assets:
        return '[ASSETS] No assets found.'
    lines = [f'[ASSETS — {len(assets)} items]']
    for a in assets:
        lines.append(
            f'• {a.name} | SKU: {a.sku or "N/A"} | Type: {a.asset_type} '
            f'| Status: {a.status.value} | Location: {a.location or "N/A"} '
            f'| Serial: {a.serial_number or "N/A"}'
        )
    return '\n'.join(lines)


def _retrieve_subscriptions(db: Session, tenant_id: str, _message: str) -> str:
    subs = (
        db.query(Subscription).filter(Subscription.tenant_id == tenant_id)
        .order_by(Subscription.created_at.desc()).limit(10).all()
    )
    if not subs:
        return '[SUBSCRIPTIONS] No subscriptions found.'
    lines = [f'[SUBSCRIPTIONS — {len(subs)} items]']
    for s in subs:
        lines.append(
            f'• {s.name} | Status: {s.status.value} | {_fmt_currency(float(s.unit_price))}/{s.interval.value} '
            f'| Next billing: {s.next_billing_date.strftime("%Y-%m-%d") if s.next_billing_date else "N/A"}'
        )
    return '\n'.join(lines)


def _retrieve_contracts(db: Session, tenant_id: str, _message: str) -> str:
    contracts = (
        db.query(Contract).filter(Contract.tenant_id == tenant_id)
        .order_by(Contract.created_at.desc()).limit(10).all()
    )
    if not contracts:
        return '[CONTRACTS] No contracts found.'
    lines = [f'[CONTRACTS — {len(contracts)} items]']
    for c in contracts:
        lines.append(
            f'• Contract {str(c.id)[:8]}… | Status: {c.status.value} '
            f'| Term: {c.term_months} months | SLA: {c.sla_tier} '
            f'| Start: {c.start_date.strftime("%Y-%m-%d") if c.start_date else "N/A"}'
        )
    return '\n'.join(lines)


def _retrieve_billing(db: Session, tenant_id: str, _message: str) -> str:
    invoices = (
        db.query(Invoice).filter(Invoice.tenant_id == tenant_id)
        .order_by(Invoice.created_at.desc()).limit(10).all()
    )
    if not invoices:
        return '[BILLING] No invoices found.'
    lines = [f'[BILLING — {len(invoices)} most recent invoices]']
    for inv in invoices:
        lines.append(
            f'• Invoice {str(inv.id)[:8]}… | {_fmt_currency(float(inv.amount))} '
            f'| Status: {inv.status.value} | Due: {inv.due_date.strftime("%Y-%m-%d") if inv.due_date else "N/A"} '
            f'| Month: {inv.billing_month}'
        )
    return '\n'.join(lines)


def _retrieve_onboarding(db: Session, tenant_id: str, _message: str) -> str:
    profile = db.query(TenantOnboarding).filter(TenantOnboarding.tenant_id == tenant_id).first()
    if not profile:
        return '[ONBOARDING] No onboarding profile found.'
    return (
        f'[ONBOARDING]\n'
        f'Organization: {profile.organization_name or "Not set"}\n'
        f'Company setup: {"Complete" if profile.company_setup_completed else "Incomplete"}\n'
        f'Payment method: {"Set up" if profile.payment_method_setup else "Not set up"}\n'
        f'Credit validation: {profile.credit_validation_status.value}\n'
        f'Tax validation: {profile.tax_validation_status.value}\n'
        f'Onboarding completed: {"Yes" if profile.onboarding_completed else "No"}'
    )


def _retrieve_cabling(db: Session, tenant_id: str, message: str) -> str:
    """Return cabling/wiring domain knowledge and any cable-related BOM data."""
    import math

    lines = ['[CABLING & WIRING KNOWLEDGE]']
    lines.append('Cable standards available:')
    lines.append('• CAT5  — up to 100 Mbps, legacy standard, $0.35/meter')
    lines.append('• CAT6  — up to 1 Gbps, recommended default, $0.55/meter')
    lines.append('• CAT6e — up to 10 Gbps, premium/future-proof, $0.80/meter')
    lines.append('')
    lines.append('Cable calculation formula:')
    lines.append('  avg_run = sqrt(floor_area_sqft) × 0.3048 m')
    lines.append('  total_cable = avg_run × wired_drops × 1.2 (slack)')
    lines.append('  cost = total_cable_meters × price_per_meter')
    lines.append('  Cabling typically contributes 10-15% of total BOM cost.')
    lines.append('')
    lines.append('Connectivity rules:')
    lines.append('• Wired devices (need CAT cable): Routers, Switches, AP uplinks, PoE cameras, POS terminals')
    lines.append('• Wireless devices (Wi-Fi, no cable): iPads, tablets, laptops on Wi-Fi, wireless sensors')
    lines.append('• Cellular devices (SIM/5G, no local cable): Cellular gateways, MiFi hotspots, SIM-enabled endpoints')
    lines.append('')
    lines.append('Topology diagram lines represent:')
    lines.append('• They are connectivity relationships (not exact physical cable routes).')
    lines.append('• Solid dark lines = Wired link')
    lines.append('• Dashed blue lines = Wireless link (Wi-Fi)')
    lines.append('• Dotted gray lines = Managed connection')
    lines.append('• Dashed orange lines = Failover path (cellular backup)')

    # If user mentions a specific area, give an estimate
    msg_lower = message.lower()
    import re
    area_match = re.search(r'(\d[\d,]*)\s*(?:sq\s*ft|sqft|square\s*feet)', msg_lower)
    if area_match:
        area = float(area_match.group(1).replace(',', ''))
        avg_run = math.sqrt(area) * 0.3048
        for cable_type, price in [('CAT5', 0.35), ('CAT6', 0.55), ('CAT6e', 0.80)]:
            # Estimate for 10 wired drops as example
            drops = 10
            total_m = round(avg_run * drops * 1.2, 1)
            cost = round(total_m * price, 2)
            lines.append(f'  Example for {int(area)} sqft / {drops} drops with {cable_type}: '
                         f'{total_m}m cable → ${cost}')

    return '\n'.join(lines)


PORTAL_KNOWLEDGE = """
SecureOffice2 Portal Overview:
- Dashboard: View your account overview at /shop/dashboard
- New Request: Start a new network design request at /shop/flow-options
- Catalog: Browse network devices (routers, switches, access points, firewalls) at /shop/routers
- Managed Services: Browse managed services (monitoring, backup, security) at /shop/services
- Cart: Review and checkout items at /shop/cart
- Orders: View order history and track deliveries at /shop/orders
- Quotes: View and manage price quotes at /shop/quotes
- Designs: View network design history at /shop/designs, create new designs at /shop/designs/new
- Lifecycle: Track contracts, subscriptions, and assets at /shop/lifecycle
- Billing: View invoices, payments, and billing overview at /shop/billing
- Support: Get help at /shop/support
- Onboarding: Complete company setup at /shop/onboarding

Key Workflows:
1. Browse Catalog → Add to Cart → Generate Quote → Accept Quote → Convert to Order
2. New Request → Network Design Builder → BOM Generation → Topology → Submit Design
3. Order placed → Workflow tracks: validation → fulfillment → installation → completion

Device Types: Routers, Switches, Access Points, Firewalls, and other network hardware.
Service Types: Managed monitoring, backup, security, and connectivity services.
"""

# Map intent to retriever
RETRIEVERS: dict[str, callable] = {
    'catalog': _retrieve_catalog,
    'cabling': _retrieve_cabling,
    'cart': _retrieve_cart,
    'orders': _retrieve_orders,
    'quotes': _retrieve_quotes,
    'designs': _retrieve_designs,
    'assets': _retrieve_assets,
    'subscriptions': _retrieve_subscriptions,
    'contracts': _retrieve_contracts,
    'billing': _retrieve_billing,
    'onboarding': _retrieve_onboarding,
}


def _build_context(db: Session, tenant_id: str, message: str) -> str:
    """Build the RAG context by retrieving relevant data."""
    intents = _detect_intents(message)
    context_parts = [PORTAL_KNOWLEDGE]

    # Retrieve data for the top 3 intents
    retrieved_intents = set()
    for intent in intents[:3]:
        if intent == 'general':
            continue
        retriever = RETRIEVERS.get(intent)
        if retriever and intent not in retrieved_intents:
            try:
                context_parts.append(retriever(db, tenant_id, message))
                retrieved_intents.add(intent)
            except Exception as exc:
                logger.warning('Retrieval error for %s: %s', intent, exc)

    return '\n\n'.join(context_parts)


def _call_openai(system_prompt: str, user_message: str) -> str:
    """Call OpenAI API for answer generation."""
    import httpx

    api_key = settings.openai_api_key
    if not api_key:
        raise ValueError('OpenAI API key not configured')

    response = httpx.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={
            'model': 'gpt-4.1-mini',
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_message},
            ],
            'temperature': 0.4,
            'max_tokens': 800,
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content']


SYSTEM_PROMPT_TEMPLATE = """You are the SecureOffice2 AI Assistant — a helpful, concise chatbot embedded in the SecureOffice2 network solutions portal.

Your job is to answer the user's question using ONLY the retrieved context below. If the context doesn't contain enough information, say so honestly — never invent data.

Rules:
- Be concise and direct. Use bullet points for lists.
- Format prices as dollar amounts.
- When referencing portal pages, include the path (e.g., /shop/routers).
- If the user asks about a specific device/order/quote, reference the data from context.
- Do not reveal raw database IDs — use short references like "Order …a1b2".
- Be friendly and professional.
- For wiring topics, use typed standards: CAT5, CAT6, CAT6e (never generic "copper wire").
- Topology lines represent relationship semantics:
  - Wired link
  - Wireless link
  - Managed connection
- If discussing cabling BOM, explain it is a derived item from office area and priced by meter.

RETRIEVED CONTEXT:
{context}
"""


class ChatbotService:
    def __init__(self, db: Session):
        self.db = db

    def ask(self, tenant_id: str, message: str, history: list[dict] | None = None) -> str:
        """Process a user question using a CrewAI multi-agent system."""
        guardrail = _check_guardrails(message)
        if guardrail:
            return guardrail

        diagram_guardrail = _check_diagram_semantics_guardrail(message)
        if diagram_guardrail:
            return diagram_guardrail

        # Delegate to CrewAI multi-agent crew
        try:
            from app.services.crew import ChatbotCrew
            import traceback

            verbose = getattr(settings, 'crewai_verbose', False)
            crew = ChatbotCrew(self.db, tenant_id, verbose=verbose)
            answer = crew.run(message, history)
        except Exception as exc:
            logger.error('CrewAI crew failed: %s\n%s', exc, traceback.format_exc())
            # Fallback: build context the old way and return a simple answer
            context = _build_context(self.db, tenant_id, message)
            answer = self._fallback_answer(message, context)

        return answer

    def _fallback_answer(self, message: str, context: str) -> str:
        """Generate a simple answer without LLM when OpenAI is unavailable."""
        intents = _detect_intents(message)
        parts = ['Here\'s what I found based on your question:\n']

        # Extract the data sections from context
        for line in context.split('\n'):
            if line.startswith('[') or line.startswith('•'):
                parts.append(line)

        if len(parts) <= 1:
            parts.append(
                'I can help you with information about devices, orders, quotes, '
                'designs, assets, subscriptions, billing, and general portal navigation. '
                'Try asking something like:\n'
                '• "What devices are available?"\n'
                '• "Show me my recent orders"\n'
                '• "What\'s in my cart?"\n'
                '• "How do I create a network design?"'
            )

        return '\n'.join(parts)
