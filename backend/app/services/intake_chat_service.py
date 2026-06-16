"""Business intake conversational service powered by CrewAI.

Runs a single-agent crew to chat with a user, extract business profile
fields, and return structured JSON the frontend can use to prefill a form.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from crewai import Crew, Process, Task

from app.services.audit_logger import audit
from app.services.crew.agents import build_intake_agent
from app.services.llm_guardrails import (
    detect_injection,
    sanitize_history,
    sanitize_user_text,
    secondary_guardrail_check,
)

logger = logging.getLogger(__name__)

# Public, unauthenticated endpoint with no keyword denylist — the deterministic
# pre-filter is the first input control here (RAG plan 0.5 / refinement #3).
INTAKE_GUARDRAIL_ANSWER = (
    "I can only help set up your business network profile. Tell me about your "
    "business — what type it is, how many locations, the square footage, and "
    "how many employees and customers you have."
)


# Output schema whitelist lives in the central guardrail policy (RAG plan 3.2).
from app.core.guardrail_policy import (  # noqa: E402
    ALLOWED_BUSINESS_TYPES,
    ALLOWED_EXTRACT_KEYS,
)


def _parse_json_safely(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from LLM output, tolerating markdown fences
    or surrounding prose."""
    if not text:
        return None

    # 1) straight parse
    try:
        return json.loads(text)
    except Exception as exc:
        logger.debug('Straight JSON parse failed, trying fences: %s', exc)

    # 2) strip markdown code fences
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception as exc:
            logger.debug('Fenced JSON parse failed, trying balanced braces: %s', exc)

    # 3) find first balanced { ... }
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    snippet = text[start : i + 1]
                    try:
                        return json.loads(snippet)
                    except Exception as exc:
                        logger.debug('Balanced-brace JSON parse failed at %d: %s', start, exc)
                        break
        start = text.find("{", start + 1)

    return None


def _sanitize_extracted(extracted: Any) -> dict[str, Any]:
    """Keep only valid keys and coerce numeric fields."""
    if not isinstance(extracted, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in extracted.items():
        if key not in ALLOWED_EXTRACT_KEYS:
            continue
        if key == "businessType":
            if isinstance(value, str) and value in ALLOWED_BUSINESS_TYPES:
                out[key] = value
            continue
        # Numeric fields
        try:
            num = int(float(value))
            if num >= 0:
                out[key] = num
        except (TypeError, ValueError):
            continue
    return out


class IntakeChatService:
    """Runs a single-agent intake crew."""

    def chat(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        current_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        history = history or []
        current_fields = current_fields or {}

        # Deterministic pre-filter, then the optional model-based guardrail (2.1).
        block_reason = detect_injection(message) or secondary_guardrail_check(message)
        if block_reason:
            logger.warning('intake guardrail blocked input: %s', block_reason)
            # 1.2: public endpoint — record blocked attempts for incident review.
            audit.log(
                'intake_blocked', status='blocked', level=logging.WARNING,
                reason=block_reason, message_len=len(message or ''),
            )
            return {
                "answer": INTAKE_GUARDRAIL_ANSWER,
                "extracted": {},
                "is_complete": False,
            }

        # Strip invisible/bidi chars before the message enters the prompt.
        message = sanitize_user_text(message)

        # 2.3: sanitize replayed history turns before they re-enter the prompt.
        history = sanitize_history(history) or []

        agent = build_intake_agent()

        history_str = "\n".join(
            f"{m.get('role', 'user').upper()}: {m.get('content', '')}"
            for m in history[-10:]
        )
        current_summary = json.dumps(
            {k: v for k, v in current_fields.items() if k in ALLOWED_EXTRACT_KEYS},
            ensure_ascii=False,
        )

        task_description = (
            f"CURRENT KNOWN FIELDS (already filled): {current_summary}\n\n"
            f"CONVERSATION SO FAR:\n{history_str or '(no prior messages)'}\n\n"
            f"USER'S LATEST MESSAGE: {message}\n\n"
            "Respond with ONLY the JSON object specified in your instructions. "
            "Do not wrap in code fences. Do not add explanations."
        )

        task = Task(
            description=task_description,
            expected_output=(
                'Strict JSON only: {"answer": "...", '
                '"extracted": {...optional fields...}, "is_complete": bool}'
            ),
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        try:
            result = crew.kickoff()
        except Exception as exc:
            logger.exception("Intake crew kickoff failed: %s", exc)
            return {
                "answer": (
                    "Sorry, I had trouble understanding that. Could you tell me "
                    "about your business type, number of locations, square footage, "
                    "and how many employees and customers you have?"
                ),
                "extracted": {},
                "is_complete": False,
            }

        raw = ""
        if hasattr(result, "raw"):
            raw = str(result.raw)
        elif hasattr(result, "output"):
            raw = str(result.output)
        else:
            raw = str(result)

        parsed = _parse_json_safely(raw.strip())

        if not isinstance(parsed, dict):
            logger.warning("Intake crew returned unparseable output: %s", raw[:200])
            return {
                "answer": raw.strip() or (
                    "Tell me a bit about your business — what type is it, "
                    "how many locations, and how many employees?"
                ),
                "extracted": {},
                "is_complete": False,
            }

        answer = str(parsed.get("answer", "")).strip()
        extracted = _sanitize_extracted(parsed.get("extracted"))
        is_complete_raw = parsed.get("is_complete", False)
        if isinstance(is_complete_raw, str):
            is_complete = is_complete_raw.strip().lower() == "true"
        else:
            is_complete = bool(is_complete_raw)

        if not answer:
            answer = (
                "Thanks — tell me more about your business so I can build the "
                "right network for you."
            )

        # 1.2: record the extraction outcome (keys only, never raw PII values).
        audit.log(
            'intake_query',
            extracted_keys=','.join(sorted(extracted)) or '-',
            is_complete=is_complete,
            answer_len=len(answer),
            message_preview=message[:200],
        )

        return {
            "answer": answer,
            "extracted": extracted,
            "is_complete": is_complete,
        }
