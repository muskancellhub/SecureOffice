"""Task factory for the CrewAI chatbot — maps detected intents to tasks."""

from crewai import Agent, Task


# Map intent keys (from chatbot_service._detect_intents) to agent roles
INTENT_TO_ROLE: dict[str, str] = {
    "catalog": "Product Catalog Specialist",
    "cabling": "Network Design Architect",
    "designs": "Network Design Architect",
    "orders": "Order & Quote Specialist",
    "quotes": "Order & Quote Specialist",
    "cart": "Order & Quote Specialist",
    "assets": "Asset & Lifecycle Manager",
    "subscriptions": "Asset & Lifecycle Manager",
    "contracts": "Asset & Lifecycle Manager",
    "billing": "Billing & Finance Specialist",
    "onboarding": "Onboarding & Portal Guide",
    "general": "Onboarding & Portal Guide",
}


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return ""
    parts = []
    for entry in history[-4:]:
        role = entry.get("role", "user").upper()
        content = entry.get("content", "")
        parts.append(f"{role}: {content}")
    return "Recent conversation:\n" + "\n".join(parts) + "\n\n"


def pick_agents_for_intents(
    intents: list[str],
    agents_by_role: dict[str, Agent],
) -> list[Agent]:
    """Return the deduplicated list of specialist agents needed for these intents."""
    seen_roles: set[str] = set()
    picked: list[Agent] = []
    for intent in intents[:3]:
        role = INTENT_TO_ROLE.get(intent, "Onboarding & Portal Guide")
        if role not in seen_roles:
            seen_roles.add(role)
            agent = agents_by_role.get(role)
            if agent:
                picked.append(agent)
    if not picked:
        fallback = agents_by_role.get("Onboarding & Portal Guide")
        if fallback:
            picked.append(fallback)
    return picked


def build_task(
    message: str,
    history: list[dict] | None,
    agent: Agent,
    prefetched_data: str = "",
) -> Task:
    """Create a CrewAI Task for a specialist agent to answer the user's question.

    The prefetched_data contains real database results so the agent doesn't need
    to call tools — it already has the data and just needs to format a response.
    """
    history_block = _format_history(history)

    # Build the data context block
    data_block = ""
    if prefetched_data:
        data_block = (
            "\n\n--- RETRIEVED DATA (from the database — use this to answer) ---\n"
            f"{prefetched_data}\n"
            "--- END OF RETRIEVED DATA ---\n\n"
        )

    return Task(
        description=(
            f"{history_block}"
            f"User question: {message}\n"
            f"{data_block}"
            f"Instructions:\n"
            f"1. Use the RETRIEVED DATA above to answer the user's question accurately\n"
            f"2. If the data contains product listings, present them as a clean bullet list "
            f"with name, price, and availability\n"
            f"3. Format prices as dollar amounts (e.g., $199.99)\n"
            f"4. Include portal navigation as markdown links like "
            f"[Browse Routers](/shop/routers) or [View Designs](/shop/designs)\n"
            f"5. Be concise and helpful — summarize, don't dump raw data\n"
            f"6. If no relevant data was found, say so honestly\n"
            f"7. You may also use your tools to get additional data if needed"
        ),
        expected_output=(
            "A clear, concise answer based on the retrieved data. "
            "Use bullet points for product/item lists. Format prices as $X.XX. "
            "Include markdown links for portal pages like [View Orders](/shop/orders). "
            "Keep it conversational and helpful."
        ),
        agent=agent,
    )
