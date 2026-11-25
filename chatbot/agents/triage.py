"""Triage agent with handoffs (the production design from notebook 04) and get_starting_agent()."""
from agents import Agent

from chatbot.agents.academy import academy_agent
from chatbot.agents.sales import services_agent
from chatbot.agents.support import opendoor_agent
from chatbot.config import MODEL
from chatbot.guardrails import INPUT_GUARDRAILS, OUTPUT_GUARDRAILS
from chatbot.prompts import TRIAGE_INSTRUCTIONS

triage_agent = Agent(
    name="Coltek Assistant",   # specialists hand back "to the Coltek Assistant", so keep this name
    instructions=TRIAGE_INSTRUCTIONS,
    model=MODEL,
    handoffs=[services_agent, academy_agent, opendoor_agent],
    input_guardrails=INPUT_GUARDRAILS,
    output_guardrails=OUTPUT_GUARDRAILS,
)

# Specialists can hand back to triage (set here because triage must exist first)
SPECIALISTS = [services_agent, academy_agent, opendoor_agent]
for _specialist in SPECIALISTS:
    _specialist.handoffs = [triage_agent]


# Short names the server (or a test) can use, plus each agent's full name
_AGENTS_BY_NAME = {
    "triage": triage_agent,
    "services": services_agent,
    "sales": services_agent,
    "academy": academy_agent,
    "opendoor": opendoor_agent,
    "support": opendoor_agent,
}
for _agent in [triage_agent, *SPECIALISTS]:
    _AGENTS_BY_NAME[_agent.name.lower()] = _agent


# Department of each agent, saved in thread metadata for reporting
DEPARTMENTS = {
    triage_agent.name: "general",
    services_agent.name: "services",
    academy_agent.name: "academy",
    opendoor_agent.name: "opendoor",
}


def department_for(agent_name: str | None) -> str:
    return DEPARTMENTS.get(agent_name or "", "general")


def get_starting_agent(name: str | None = None) -> Agent:
    """Return the agent a run should start with.

    None (a new conversation) -> triage.
    A short name ("services", "sales", "academy", "opendoor", "support", "triage") or an agent's
    full name (e.g. result.last_agent.name saved from the previous turn) -> that agent.
    An unknown name -> triage, so a stale saved name never breaks a conversation.
    """
    if not name:
        return triage_agent
    return _AGENTS_BY_NAME.get(name.strip().lower(), triage_agent)
