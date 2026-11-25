"""Services & Sales specialist: Coltek Technologies builds and corporate training."""
from agents import Agent

from chatbot.agents.common import file_search_for
from chatbot.config import MODEL
from chatbot.guardrails import INPUT_GUARDRAILS, OUTPUT_GUARDRAILS
from chatbot.prompts import SERVICES_INSTRUCTIONS
from chatbot.tools import save_lead

services_agent = Agent(
    name="Services and Sales Specialist",   # no '&': the handoff tool name is built from this
    handoff_description="Handles requests for Coltek to build software, websites, apps, AI solutions, school/church systems, corporate training, and quotes.",
    instructions=SERVICES_INSTRUCTIONS,
    model=MODEL,
    tools=[file_search_for("services", "company"), save_lead],
    input_guardrails=INPUT_GUARDRAILS,      # from turn 2 a run can start here (result.last_agent)
    output_guardrails=OUTPUT_GUARDRAILS,
)
# handoffs (back to triage) are set in chatbot/agents/triage.py
