"""Single source of truth for RAG/LLM guardrail policy (RAG plan 3.2).

Principle #3 from the security docs — separate policy from intelligence. All
denylists, allowlists, thresholds, and rate limits that govern the LLM surfaces
live here so policy is auditable in one place and both RAG surfaces share it.

This module is pure data (no app imports) to stay free of circular imports.
The logic that applies these values lives in app/services/llm_guardrails.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Topic denylist (chatbot) — substring refusal list.
# ---------------------------------------------------------------------------
BLOCKED_TOPICS: tuple[str, ...] = (
    # Off-topic / harmful
    "hack", "exploit", "vulnerability", "bypass", "jailbreak",
    "password crack", "brute force", "ddos", "denial of service",
    # Personal / sensitive
    "social security", "ssn", "credit card number", "bank account",
    "personal address", "home address", "date of birth",
    # Competitor intelligence
    "competitor pricing", "competitor strategy",
    # Medical / legal advice
    "medical advice", "legal advice", "lawsuit", "diagnosis",
)

# ---------------------------------------------------------------------------
# Prompt-injection / override phrases (deterministic pre-filter + history).
# ---------------------------------------------------------------------------
INJECTION_PHRASES: tuple[str, ...] = (
    "ignore previous",
    "ignore prior",
    "ignore all previous",
    "ignore the above",
    "disregard previous",
    "disregard the above",
    "disregard all",
    "forget previous",
    "forget the above",
    "system prompt",
    "developer mode",
    "you are now",
    "new instructions",
    "override your",
    "reveal your instructions",
    "print your instructions",
    "repeat the above",
    "repeat your instructions",
)

# Soft signals that make an input worth a secondary classifier look (2.1).
BORDERLINE_SIGNALS: tuple[str, ...] = (
    "prompt", "instruction", "instructions", "system", "role", "roleplay",
    "pretend", "act as", "rules", "policy", "policies", "guardrail",
    "jailbreak", "dan mode", "bypass", "restriction", "unfiltered",
    "as an ai", "you must", "from now on",
)

# Strings that must never appear in a user-facing answer (output leakage, 1.3).
OUTPUT_LEAK_MARKERS: tuple[str, ...] = (
    "retrieved data",
    "retrieved context",
    "end of retrieved",
    "--- retrieved",
    "system prompt",
    "you are the secureoffice2 ai assistant",
)

# Regulated topics that trigger the informational-not-advice disclaimer (2.4).
ADVICE_TOPIC_PATTERN: str = (
    r"\b(invoice|billing|payment|refund|tax|contract|sla|legal|lawsuit|"
    r"liabilit|financ|interest rate|apr|credit)\w*"
)

# ---------------------------------------------------------------------------
# Intake extraction allow-lists (output schema whitelist).
# ---------------------------------------------------------------------------
ALLOWED_EXTRACT_KEYS: frozenset[str] = frozenset({
    "businessType",
    "locations",
    "squareFootage",
    "employees",
    "peakCustomers",
    "avgDailyCustomers",
})

ALLOWED_BUSINESS_TYPES: frozenset[str] = frozenset({
    "Restaurant / QSR",
    "Grocery store",
    "Retail store",
    "Office",
    "Gym",
    "Hotel",
    "Convenience store",
    "Warehouse",
})

# ---------------------------------------------------------------------------
# Numeric thresholds.
# ---------------------------------------------------------------------------
BASE64_MIN_LEN: int = 24          # min length of a base64 blob to inspect
HEX_MIN_LEN: int = 40             # min length of a hex blob to inspect
FIELD_MAX_LEN: int = 200          # cap on a single retrieved free-text field
HISTORY_TURN_MAX_LEN: int = 2000  # cap on a replayed conversation turn

# ---------------------------------------------------------------------------
# Rate limits for the LLM-backed endpoints (merged into the middleware table).
# Values are (max_requests, window_seconds).
# ---------------------------------------------------------------------------
LLM_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/intake/chat": (5, 60),
    "/anam/session": (5, 60),
    "/anam/parse-intent": (10, 60),
    "/chatbot/ask": (30, 60),
    # Authenticated + tenant-scoped, so it can be looser than the public intake
    # surface. AI design generation is an explicit user action, not per-keystroke.
    "/designs/ai-generate": (10, 60),
}
