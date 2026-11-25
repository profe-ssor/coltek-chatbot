"""OpenDoor specialist: church management software demos, features, login and support."""
from agents import Agent

from chatbot.agents.common import file_search_for
from chatbot.config import MODEL
from chatbot.guardrails import INPUT_GUARDRAILS, OUTPUT_GUARDRAILS
from chatbot.prompts import OPENDOOR_INSTRUCTIONS
from chatbot.tools import request_opendoor_demo

opendoor_agent = Agent(
    name="OpenDoor Specialist",
    handoff_description="Handles OpenDoor church management software: features, demos, pricing, login problems, support.",
    instructions=OPENDOOR_INSTRUCTIONS,
    model=MODEL,
    tools=[file_search_for("opendoor", "company"), request_opendoor_demo],
    input_guardrails=INPUT_GUARDRAILS,
    output_guardrails=OUTPUT_GUARDRAILS,
)
# handoffs (back to triage) are set in chatbot/agents/triage.py
