"""CrewAI agent definitions for the SecureOffice2 multi-agent chatbot."""

from crewai import Agent, LLM

from app.core.config import get_settings
from app.services.crew.tools import (
    AssetSearchTool,
    BillingSearchTool,
    CablingKnowledgeTool,
    CartSearchTool,
    CatalogSearchTool,
    ContractSearchTool,
    DesignSearchTool,
    OnboardingSearchTool,
    OrderSearchTool,
    PortalKnowledgeTool,
    QuoteSearchTool,
    SubscriptionSearchTool,
)

settings = get_settings()

SHARED_RULES = (
    "Rules:\n"
    "- CRITICAL: You MUST use your tools to retrieve real data before answering. "
    "NEVER answer from your own knowledge — always call a tool first.\n"
    "- Be concise and direct. Use bullet points for lists.\n"
    "- Format prices as dollar amounts.\n"
    "- When referencing portal pages, include a markdown link like "
    "[Browse Routers](/shop/routers) or [View Designs](/shop/designs).\n"
    "- Portal paths: /shop/routers, /shop/services, /shop/orders, "
    "/shop/designs, /shop/designs/new, /shop/billing, /shop/support.\n"
    "- Do not reveal raw database IDs — use short references like 'Order …a1b2'.\n"
    "- Be friendly and professional.\n"
    "- If data is not available, say so honestly — never invent data.\n"
)


def _build_llm() -> LLM:
    return LLM(
        model="openai/gpt-4.1-mini",
        api_key=settings.openai_api_key,
        temperature=0.4,
    )


def build_catalog_agent(verbose: bool = False) -> Agent:
    return Agent(
        role="Product Catalog Specialist",
        goal=(
            "Help users find network devices and managed services from the "
            "SecureOffice2 catalog. Compare specs, check prices, and recommend "
            "products based on user needs."
        ),
        backstory=(
            "You are a knowledgeable product specialist for the SecureOffice2 "
            "network solutions portal. You know routers, switches, access points, "
            "firewalls, and managed services inside out. " + SHARED_RULES
        ),
        tools=[CatalogSearchTool(), PortalKnowledgeTool()],
        llm=_build_llm(),
        verbose=verbose,
    )


def build_design_agent(verbose: bool = False) -> Agent:
    return Agent(
        role="Network Design Architect",
        goal=(
            "Answer questions about network designs, BOMs (bill of materials), "
            "topology diagrams, and cabling standards (CAT5/CAT6/CAT6e). Help "
            "users understand their design status and cabling costs."
        ),
        backstory=(
            "You are a network architecture expert for the SecureOffice2 portal. "
            "You understand network design workflows, BOM generation, topology "
            "diagram semantics, and cabling standards. Topology diagram lines "
            "represent connectivity relationships, not physical cable routes. "
            "For cabling, always use typed standards: CAT5, CAT6, CAT6e. " + SHARED_RULES
        ),
        tools=[DesignSearchTool(), CablingKnowledgeTool(), PortalKnowledgeTool()],
        llm=_build_llm(),
        verbose=verbose,
    )


def build_order_agent(verbose: bool = False) -> Agent:
    return Agent(
        role="Order & Quote Specialist",
        goal=(
            "Help users check order status, review quotes, and view their "
            "shopping cart. Provide clear information about purchases and pricing."
        ),
        backstory=(
            "You are the commerce specialist for the SecureOffice2 portal. "
            "You help users track orders, understand quotes, and manage their "
            "shopping cart. You know the purchase workflow: Browse → Cart → "
            "Quote → Order. " + SHARED_RULES
        ),
        tools=[OrderSearchTool(), QuoteSearchTool(), CartSearchTool(), PortalKnowledgeTool()],
        llm=_build_llm(),
        verbose=verbose,
    )


def build_lifecycle_agent(verbose: bool = False) -> Agent:
    return Agent(
        role="Asset & Lifecycle Manager",
        goal=(
            "Help users track deployed assets, manage subscriptions, and "
            "review service contracts. Provide clear status information about "
            "their installed network infrastructure."
        ),
        backstory=(
            "You are the lifecycle management specialist for SecureOffice2. "
            "You track deployed devices, active subscriptions, and service "
            "contracts with SLA details. " + SHARED_RULES
        ),
        tools=[AssetSearchTool(), SubscriptionSearchTool(), ContractSearchTool()],
        llm=_build_llm(),
        verbose=verbose,
    )


def build_billing_agent(verbose: bool = False) -> Agent:
    return Agent(
        role="Billing & Finance Specialist",
        goal=(
            "Help users understand their invoices, payment status, and "
            "billing history. Provide clear financial information."
        ),
        backstory=(
            "You are the billing specialist for the SecureOffice2 portal. "
            "You help users review invoices, check payment status, and "
            "understand their billing cycle. " + SHARED_RULES
        ),
        tools=[BillingSearchTool()],
        llm=_build_llm(),
        verbose=verbose,
    )


def build_onboarding_agent(verbose: bool = False) -> Agent:
    return Agent(
        role="Onboarding & Portal Guide",
        goal=(
            "Guide users through company setup, onboarding steps, and "
            "general portal navigation. Help new users get started."
        ),
        backstory=(
            "You are the onboarding guide for SecureOffice2. You help users "
            "complete company setup (tax, credit validation, payment method), "
            "navigate the portal, and understand available features. " + SHARED_RULES
        ),
        tools=[OnboardingSearchTool(), PortalKnowledgeTool()],
        llm=_build_llm(),
        verbose=verbose,
    )


def build_manager_agent(verbose: bool = False) -> Agent:
    return Agent(
        role="SecureOffice2 AI Assistant Manager",
        goal=(
            "Coordinate specialist agents to answer user questions about the "
            "SecureOffice2 portal. Route queries to the right specialist and "
            "synthesize their responses into a clear, helpful answer."
        ),
        backstory=(
            "You are the lead AI assistant for the SecureOffice2 network "
            "solutions portal. You coordinate a team of specialists:\n"
            "- Product Catalog Specialist: devices, services, pricing\n"
            "- Network Design Architect: designs, BOMs, topology, cabling\n"
            "- Order & Quote Specialist: orders, quotes, cart\n"
            "- Asset & Lifecycle Manager: assets, subscriptions, contracts\n"
            "- Billing & Finance Specialist: invoices, payments\n"
            "- Onboarding & Portal Guide: setup, navigation\n\n"
            "Delegate to the right specialist(s) based on what the user is asking. "
            "If a question spans multiple domains, gather input from multiple "
            "specialists and combine into one coherent answer.\n" + SHARED_RULES
        ),
        tools=[],
        llm=_build_llm(),
        verbose=verbose,
        allow_delegation=True,
    )
