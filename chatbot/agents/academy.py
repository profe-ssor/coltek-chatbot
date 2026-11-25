"""Code Academy advisor: Coltek Code Academy courses and enrolment."""
from agents import Agent

from chatbot.agents.common import file_search_for
from chatbot.config import MODEL
from chatbot.guardrails import INPUT_GUARDRAILS, OUTPUT_GUARDRAILS
from chatbot.prompts import ACADEMY_INSTRUCTIONS
from chatbot.tools import check_course_intake, save_lead

academy_agent = Agent(
    name="Code Academy Advisor",
    handoff_description="Handles Coltek Code Academy courses: choosing a course, enrolment, dates, fees, beginners, assessments, certificates.",
    instructions=ACADEMY_INSTRUCTIONS,
    model=MODEL,
    tools=[file_search_for("academy", "company"), check_course_intake, save_lead],
    input_guardrails=INPUT_GUARDRAILS,
    output_guardrails=OUTPUT_GUARDRAILS,
)
# handoffs (back to triage) are set in chatbot/agents/triage.py
