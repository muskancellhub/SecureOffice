"""Main crew orchestrator — assembles agents, tasks, and runs the crew."""

import logging

from crewai import Crew, Process
from sqlalchemy.orm import Session

from app.services.chatbot_service import _detect_intents, _build_context, RETRIEVERS
from app.services.crew.agents import (
    build_billing_agent,
    build_catalog_agent,
    build_design_agent,
    build_lifecycle_agent,
    build_manager_agent,
    build_onboarding_agent,
    build_order_agent,
)
from app.services.crew.tasks import (
    build_task,
    pick_agents_for_intents,
)
from app.services.crew.tools import set_crew_context

logger = logging.getLogger(__name__)

# Map intent keys to their retriever functions (same as chatbot_service RETRIEVERS)
INTENT_RETRIEVER_KEY = {
    "catalog": "catalog",
    "cabling": "cabling",
    "designs": "designs",
    "orders": "orders",
    "quotes": "quotes",
    "cart": "cart",
    "assets": "assets",
    "subscriptions": "subscriptions",
    "contracts": "contracts",
    "billing": "billing",
    "onboarding": "onboarding",
}


class ChatbotCrew:
    """Orchestrates a CrewAI multi-agent system to answer chatbot queries."""

    def __init__(self, db: Session, tenant_id: str, verbose: bool = False):
        self.db = db
        self.tenant_id = tenant_id
        self.verbose = verbose

        # Build all specialist agents
        self.catalog_agent = build_catalog_agent(verbose)
        self.design_agent = build_design_agent(verbose)
        self.order_agent = build_order_agent(verbose)
        self.lifecycle_agent = build_lifecycle_agent(verbose)
        self.billing_agent = build_billing_agent(verbose)
        self.onboarding_agent = build_onboarding_agent(verbose)
        self.manager_agent = build_manager_agent(verbose)

        # Index agents by role for task routing
        self.agents_by_role: dict = {
            a.role: a
            for a in [
                self.catalog_agent,
                self.design_agent,
                self.order_agent,
                self.lifecycle_agent,
                self.billing_agent,
                self.onboarding_agent,
            ]
        }

    def _prefetch_context(self, message: str, intents: list[str]) -> str:
        """Pre-fetch relevant data from the database so agents have real data.

        This is more reliable than hoping the LLM will call tools — we inject
        the retrieved data directly into the task description.
        """
        context_parts = []
        retrieved = set()

        for intent in intents[:3]:
            if intent == "general":
                continue
            retriever_key = INTENT_RETRIEVER_KEY.get(intent)
            retriever = RETRIEVERS.get(retriever_key or intent)
            if retriever and intent not in retrieved:
                try:
                    data = retriever(self.db, self.tenant_id, message)
                    if data and data.strip():
                        context_parts.append(data)
                        retrieved.add(intent)
                except Exception as exc:
                    logger.warning("Pre-fetch error for %s: %s", intent, exc)

        return "\n\n".join(context_parts)

    def run(self, message: str, history: list[dict] | None = None) -> str:
        """Run the multi-agent crew and return the answer string."""

        # Inject DB context for tools (thread-local) — tools can still be used
        set_crew_context(self.db, self.tenant_id)

        # Detect intents using the existing keyword matcher
        intents = _detect_intents(message)
        logger.info("CrewAI intents detected: %s for message: %s", intents, message[:80])
        if history:
            logger.info("CrewAI conversation history: %d exchanges", len(history))

        # Pre-fetch data from DB so agents have real data to work with
        prefetched_data = self._prefetch_context(message, intents)
        logger.info("CrewAI pre-fetched %d chars of context", len(prefetched_data))

        # Pick the specialist agent(s) needed
        picked_agents = pick_agents_for_intents(intents, self.agents_by_role)
        logger.info("CrewAI agents picked: %s", [a.role for a in picked_agents])

        if len(picked_agents) == 1:
            # Single-agent: run sequentially with just that specialist
            task = build_task(message, history, picked_agents[0], prefetched_data)
            crew = Crew(
                agents=[picked_agents[0]],
                tasks=[task],
                process=Process.sequential,
                verbose=self.verbose,
            )
        else:
            # Multi-agent: use hierarchical process with manager
            # NOTE: manager_agent must NOT be in the agents list — CrewAI validates this
            tasks = [build_task(message, history, agent, prefetched_data) for agent in picked_agents]
            crew = Crew(
                agents=picked_agents,
                tasks=tasks,
                process=Process.hierarchical,
                manager_agent=self.manager_agent,
                verbose=self.verbose,
            )

        result = crew.kickoff()

        # CrewAI returns a CrewOutput — extract the raw string
        answer = None

        if hasattr(result, 'output'):
            answer = result.output
        elif hasattr(result, 'raw'):
            answer = result.raw
        else:
            answer = str(result)

        answer = str(answer).strip() if answer else ""

        if not answer:
            answer = (
                "I wasn't able to find specific information for your question. "
                "Try asking about devices, orders, designs, billing, or portal navigation."
            )

        logger.info("CrewAI answer generated: %d chars", len(answer))
        return answer
