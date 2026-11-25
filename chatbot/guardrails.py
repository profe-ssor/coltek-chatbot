"""Input and output guardrails, their output models, the fallback messages and safe_run (notebook 05).

Input guardrails (on the first agent of every run):
    sensitive_data_guardrail  regex, no LLM: card numbers, PINs/passwords, OTP codes
    classifier_guardrail      LLM: off_topic, abusive, injection
Output guardrails (on every agent that can give the final answer):
    price_date_guardrail      regex, no LLM: prices and dates not in the courses table
    checker_guardrail         LLM: promises, legal advice, leaked instructions, wrong company, asking for secrets
"""
import asyncio
import re
from typing import Literal

from pydantic import BaseModel
from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    Runner,
    input_guardrail,
    output_guardrail,
)

from sqlmodel import select

from chatbot.config import GUARDRAIL_MODEL
from chatbot.db import Course, get_session
from chatbot.prompts import CHECKER_INSTRUCTIONS, CLASSIFIER_INSTRUCTIONS


# ---------------------------------------------------------------------------
# Output models for the two LLM guardrail agents
# ---------------------------------------------------------------------------

class InputCheck(BaseModel):
    category: Literal["allowed", "off_topic", "abusive", "injection"]
    is_blocked: bool
    reason: str        # short explanation, under 15 words
    language: str      # e.g. "English", "Twi", "Pidgin"


class OutputCheck(BaseModel):
    is_unsafe: bool
    issue: Literal["none", "promise", "legal_advice", "leaked_instructions", "wrong_company", "asked_for_secret"]
    explanation: str   # short, under 15 words


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def last_user_message(input) -> str:
    """The visitor's latest message (input can be a plain string or a conversation list)."""
    if isinstance(input, str):
        return input
    for item in reversed(input):
        if isinstance(item, dict) and item.get("role") == "user":
            return str(item.get("content", ""))
    return ""


# ---------------------------------------------------------------------------
# Input guardrail 1: sensitive data (regex, no LLM)
# ---------------------------------------------------------------------------

CARD_NUMBER = re.compile(r"\b(?:\d[ -]?){13,19}\b")                                          # 13-19 digits
SECRET = re.compile(r"\b(pin|password|passcode)\s*(is|:|=)\s*\S+", re.IGNORECASE)            # "PIN is 4821"
OTP_CODE = re.compile(r"\b(otp|one[- ]time code|verification code)\D{0,15}\d{4,8}\b", re.IGNORECASE)  # "OTP is 123456"


def find_sensitive_data(text: str) -> str | None:
    """Return what kind of sensitive data is in the text, or None if there is none."""
    if CARD_NUMBER.search(text):
        return "card number"
    if SECRET.search(text):
        return "PIN or password"
    if OTP_CODE.search(text):
        return "OTP code"
    return None


@input_guardrail(run_in_parallel=False)   # check BEFORE the agent starts, so the agent never sees the PIN
async def sensitive_data_guardrail(ctx, agent, input):
    found = find_sensitive_data(last_user_message(input))
    return GuardrailFunctionOutput(
        output_info={"reason": "sensitive_data", "found": found},
        tripwire_triggered=found is not None,
    )


# ---------------------------------------------------------------------------
# Input guardrail 2: LLM classifier
# ---------------------------------------------------------------------------

input_classifier = Agent(
    name="Input Classifier",
    instructions=CLASSIFIER_INSTRUCTIONS,
    model=GUARDRAIL_MODEL,
    output_type=InputCheck,
)


@input_guardrail(run_in_parallel=False)   # a blocked message never reaches the agent or its tools
async def classifier_guardrail(ctx, agent, input):
    result = await Runner.run(input_classifier, last_user_message(input), context=ctx.context)
    check = result.final_output
    return GuardrailFunctionOutput(
        output_info=check,
        tripwire_triggered=check.is_blocked,
    )


# ---------------------------------------------------------------------------
# Output guardrail 1: prices and dates (regex, no LLM)
# ---------------------------------------------------------------------------

PRICE = re.compile(r"(?:GHS|GH₵|GH¢|₵)\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:cedis?|GHS)", re.IGNORECASE)

MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
          "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
MONTH_NAMES = "|".join(MONTHS)
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + MONTH_NAMES + r")\b", re.IGNORECASE)   # 18 January
MONTH_DAY = re.compile(r"\b(" + MONTH_NAMES + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE)            # January 18
ISO_DATE = re.compile(r"\b\d{4}-(\d{2})-(\d{2})\b")                                                        # 2027-01-18


def find_prices(text: str) -> list[float]:
    """Every GHS/cedi amount in the text as a number, e.g. 'GHS 3,500' -> 3500.0"""
    amounts = []
    for match in PRICE.finditer(text):
        number = match.group(1) or match.group(2)
        amounts.append(float(number.replace(",", "")))
    return amounts


def find_dates(text: str) -> list[tuple[int, int]]:
    """Every specific date in the text as (month, day), e.g. '18 January' -> (1, 18)"""
    dates = []
    for day, month in DAY_MONTH.findall(text):
        dates.append((MONTHS[month.lower()], int(day)))
    for month, day in MONTH_DAY.findall(text):
        dates.append((MONTHS[month.lower()], int(day)))
    for month, day in ISO_DATE.findall(text):
        dates.append((int(month), int(day)))
    return dates


# Prices and dates that are always allowed, apart from what is in the courses table
EXTRA_APPROVED_PRICES: list[float] = []                      # add confirmed prices from the knowledge files here
EXTRA_APPROVED_DATES = find_dates("5 November 2025")         # Coltek's registration date (STABLE FACTS)


def approved_prices() -> list[float]:
    """Course fees and amounts in payment options, read from the courses table on every check."""
    prices = list(EXTRA_APPROVED_PRICES)
    with get_session() as session:
        for course in session.exec(select(Course)):
            if course.fee_ghs is not None:
                prices.append(float(course.fee_ghs))
            if course.payment_options:
                prices += find_prices(course.payment_options)   # e.g. "2 instalments of GHS 1,800"
    return prices


def approved_dates() -> list[tuple[int, int]]:
    """Course start dates and application deadlines from the courses table, as (month, day)."""
    dates = list(EXTRA_APPROVED_DATES)
    with get_session() as session:
        for course in session.exec(select(Course)):
            for day in (course.next_start_date, course.application_deadline):
                if day is not None:
                    dates.append((day.month, day.day))
    return dates


def find_unapproved(text: str) -> dict | None:
    """Return a problem dict if the reply has a price or date we did not approve, else None."""
    prices_in_reply = find_prices(text)
    if prices_in_reply:
        allowed = approved_prices()
        for amount in prices_in_reply:
            if amount not in allowed:
                return {"reason": "unapproved_price", "found": amount}

    dates_in_reply = find_dates(text)
    if dates_in_reply:
        allowed = approved_dates()
        for date in dates_in_reply:
            if date not in allowed:
                return {"reason": "unapproved_date", "found": date}
    return None


@output_guardrail
async def price_date_guardrail(ctx, agent, output):
    problem = await asyncio.to_thread(find_unapproved, str(output))   # DB read off the event loop
    return GuardrailFunctionOutput(
        output_info=problem or {"reason": "ok"},
        tripwire_triggered=problem is not None,
    )


# ---------------------------------------------------------------------------
# Output guardrail 2: LLM checker
# ---------------------------------------------------------------------------

output_checker = Agent(
    name="Output Checker",
    instructions=CHECKER_INSTRUCTIONS,
    model=GUARDRAIL_MODEL,
    output_type=OutputCheck,
)


async def check_reply(text: str) -> OutputCheck:
    """Run the output checker on a reply and return the OutputCheck."""
    result = await Runner.run(output_checker, text)
    return result.final_output


@output_guardrail
async def checker_guardrail(ctx, agent, output):
    check = await check_reply(str(output))
    return GuardrailFunctionOutput(
        output_info=check,
        tripwire_triggered=check.is_unsafe,
    )


INPUT_GUARDRAILS = [sensitive_data_guardrail, classifier_guardrail]
OUTPUT_GUARDRAILS = [price_date_guardrail, checker_guardrail]


# ---------------------------------------------------------------------------
# Fallback messages: what the visitor sees when a guardrail trips
# ---------------------------------------------------------------------------

FALLBACKS = {
    # input
    "off_topic": "I'm Coltek's assistant, so I can only help with our software services, Coltek Code Academy courses and OpenDoor. Is there something in those areas I can help you with?",
    "abusive": "I'm here to help with Coltek's services, courses and OpenDoor. If you'd like to continue, I'm happy to help. You can also reach the team on +233 54 936 1771.",
    "injection": "I can't change how I work, but I'm happy to help with Coltek's services, courses or OpenDoor. What would you like to know?",
    "sensitive_data": "Please don't share PINs, passwords or card numbers here, and I haven't stored what you sent. For payment or account help, contact the team directly on +233 54 936 1771 or support@open-door.site.",
    # output
    "unapproved_price": "Let me double-check the exact fee with the team before I give you a firm answer. Would you like them to contact you?",
    "unapproved_date": "Let me double-check the exact date with the team before I give you a firm answer. Would you like them to contact you?",
    "promise": "I can't promise that, but the team can tell you exactly what to expect. Would you like them to contact you?",
    "legal_advice": "That's a question the Coltek team should answer properly. Would you like them to contact you?",
    "leaked_instructions": "I'm happy to help with Coltek's services, courses or OpenDoor. What would you like to know?",
    "wrong_company": "Just to be clear, I'm the assistant for Coltek Technologies in Accra, Ghana. How can I help you?",
    "asked_for_secret": "Please never share passwords, PINs, OTP codes or card numbers with anyone, including us. How else can I help?",
}

DEFAULT_FALLBACK = "Let me double-check that with the team before I give you a firm answer. Would you like them to contact you?"


def get_reason(info) -> str:
    """Read the block reason from a guardrail's output_info."""
    if isinstance(info, dict):            # regex guardrails return a dict
        return info["reason"]
    if isinstance(info, InputCheck):      # input classifier
        return info.category
    return info.issue                     # output checker (OutputCheck)


# ---------------------------------------------------------------------------
# safe_run: what the server calls instead of Runner.run
# ---------------------------------------------------------------------------

async def safe_run(agent, input, **run_kwargs) -> dict:
    """Run the agent. If a guardrail trips, return a friendly fallback instead of raising.

    Returns {"reply", "blocked", "reason", "guardrail", "result"}.
    "result" is the RunResult when the run finished, else None.
    """
    try:
        result = await Runner.run(agent, input, **run_kwargs)
        return {"reply": result.final_output, "blocked": False, "reason": None,
                "guardrail": None, "result": result}
    except InputGuardrailTripwireTriggered as e:
        guardrail_name = e.guardrail_result.guardrail.get_name()
        reason = get_reason(e.guardrail_result.output.output_info)
    except OutputGuardrailTripwireTriggered as e:
        guardrail_name = e.guardrail_result.guardrail.get_name()
        reason = get_reason(e.guardrail_result.output.output_info)

    return {"reply": FALLBACKS.get(reason, DEFAULT_FALLBACK), "blocked": True, "reason": reason,
            "guardrail": guardrail_name, "result": None}
