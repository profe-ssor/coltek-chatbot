"""Smoke test: one real question through the real triage agent (calls the OpenAI API, costs a little).

Run: pytest tests/test_smoke.py
Skipped automatically if OPENAI_API_KEY or VECTOR_STORE_ID is missing.
"""
import asyncio

import pytest

from chatbot.config import settings

pytestmark = [
    pytest.mark.live,   # real API call: only runs with -m live (make test-live / make test-smoke)
    pytest.mark.skipif(
        not (settings.openai_api_key and settings.vector_store_id),
        reason="needs OPENAI_API_KEY and VECTOR_STORE_ID in .env",
    ),
]


def test_triage_answers_a_general_question():
    from chatbot.agents import get_starting_agent, triage_agent
    from chatbot.guardrails import safe_run

    agent = get_starting_agent(None)
    assert agent is triage_agent

    out = asyncio.run(safe_run(agent, "Where is Coltek located?"))

    assert out["blocked"] is False, f"blocked by {out['guardrail']}: {out['reason']}"
    assert out["result"].last_agent is triage_agent     # general questions stay with triage
    assert "Madina" in out["reply"] or "Accra" in out["reply"]
