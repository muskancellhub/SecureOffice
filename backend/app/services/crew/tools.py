"""CrewAI tool wrappers around existing database retriever functions.

Each tool wraps a retriever from chatbot_service.py, using a thread-local
DB session and tenant_id injected at crew-construction time.
"""

import threading
from typing import Any

from crewai.tools import BaseTool
from pydantic import Field
from sqlalchemy.orm import Session

from app.services.chatbot_service import (
    PORTAL_KNOWLEDGE,
    _retrieve_assets,
    _retrieve_billing,
    _retrieve_cabling,
    _retrieve_cart,
    _retrieve_catalog,
    _retrieve_contracts,
    _retrieve_designs,
    _retrieve_onboarding,
    _retrieve_orders,
    _retrieve_quotes,
    _retrieve_subscriptions,
)

# ---------------------------------------------------------------------------
# Thread-local storage for DB session + tenant during a crew run
# ---------------------------------------------------------------------------
_ctx = threading.local()


def set_crew_context(db: Session, tenant_id: str) -> None:
    """Set the DB session and tenant for the current crew execution."""
    _ctx.db = db
    _ctx.tenant_id = tenant_id


def _get_db() -> Session:
    return getattr(_ctx, "db", None)


def _get_tenant() -> str:
    return getattr(_ctx, "tenant_id", "")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

class CatalogSearchTool(BaseTool):
    name: str = "catalog_search"
    description: str = (
        "Search the product catalog for network devices (routers, switches, "
        "access points, firewalls) and managed services. Pass the user's "
        "question as input to get matching products with prices and specs."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_catalog(db, _get_tenant(), argument)


class DesignSearchTool(BaseTool):
    name: str = "design_search"
    description: str = (
        "Look up the user's network designs, including design name, status, "
        "and creation date. Pass the user's question as input."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_designs(db, _get_tenant(), argument)


class CablingKnowledgeTool(BaseTool):
    name: str = "cabling_knowledge"
    description: str = (
        "Get domain knowledge about cabling standards (CAT5, CAT6, CAT6e), "
        "pricing, cable calculation formulas, and topology diagram semantics. "
        "Pass the user's question for area-based cost estimates."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_cabling(db, _get_tenant(), argument)


class OrderSearchTool(BaseTool):
    name: str = "order_search"
    description: str = (
        "Look up the user's recent orders including status, item count, "
        "and creation date. Pass the user's question as input."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_orders(db, _get_tenant(), argument)


class QuoteSearchTool(BaseTool):
    name: str = "quote_search"
    description: str = (
        "Look up the user's price quotes including status, one-time total, "
        "monthly total, and creation date. Pass the user's question as input."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_quotes(db, _get_tenant(), argument)


class CartSearchTool(BaseTool):
    name: str = "cart_search"
    description: str = (
        "View the user's current shopping cart contents including items, "
        "quantities, prices, and subtotals."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_cart(db, _get_tenant(), argument)


class AssetSearchTool(BaseTool):
    name: str = "asset_search"
    description: str = (
        "Look up deployed assets (installed network devices) including SKU, "
        "type, status, location, and serial number."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_assets(db, _get_tenant(), argument)


class SubscriptionSearchTool(BaseTool):
    name: str = "subscription_search"
    description: str = (
        "Look up the user's active subscriptions including name, status, "
        "price, billing interval, and next billing date."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_subscriptions(db, _get_tenant(), argument)


class ContractSearchTool(BaseTool):
    name: str = "contract_search"
    description: str = (
        "Look up the user's service contracts including status, term length, "
        "SLA tier, and start date."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_contracts(db, _get_tenant(), argument)


class BillingSearchTool(BaseTool):
    name: str = "billing_search"
    description: str = (
        "Look up recent invoices and billing information including amounts, "
        "status, due dates, and billing months."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_billing(db, _get_tenant(), argument)


class OnboardingSearchTool(BaseTool):
    name: str = "onboarding_search"
    description: str = (
        "Check the user's company onboarding/setup status including "
        "organization name, payment method, credit/tax validation, "
        "and overall completion status."
    )

    def _run(self, argument: str) -> str:
        db = _get_db()
        if not db:
            return "[ERROR] Database session not available."
        return _retrieve_onboarding(db, _get_tenant(), argument)


class PortalKnowledgeTool(BaseTool):
    name: str = "portal_knowledge"
    description: str = (
        "Get general information about the SecureOffice2 portal including "
        "page navigation paths, key workflows, device types, and service types."
    )

    def _run(self, argument: str) -> str:
        return PORTAL_KNOWLEDGE
