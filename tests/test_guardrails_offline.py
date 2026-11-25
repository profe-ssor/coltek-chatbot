"""Offline tests for the regex guardrails: no API calls, no cost.

Run: pytest tests/test_guardrails_offline.py
All names and numbers below are fake. The card number is the standard 4111... test number.
"""
import asyncio
import datetime as dt

import pytest
from agents import Agent, RunContextWrapper

from sqlmodel import Session, select

from chatbot.db import Course
from chatbot.guardrails import (
    FALLBACKS,
    approved_dates,
    approved_prices,
    find_sensitive_data,
    find_unapproved,
    last_user_message,
    price_date_guardrail,
    sensitive_data_guardrail,
)

# A dummy agent and context: the guardrail .run() methods need them, but no model is called
DUMMY_AGENT = Agent(name="Test Agent")


def run_input_guardrail(message):
    result = asyncio.run(sensitive_data_guardrail.run(DUMMY_AGENT, message, RunContextWrapper(context=None)))
    return result.output


def run_output_guardrail(reply):
    result = asyncio.run(price_date_guardrail.run(RunContextWrapper(context=None), DUMMY_AGENT, reply))
    return result.output


# ---------------------------------------------------------------------------
# Sensitive data (input)
# ---------------------------------------------------------------------------

SENSITIVE_MESSAGES = [
    ("My MoMo PIN is 4821, can you check my payment?", "PIN or password"),
    ("Here is my card: 4111 1111 1111 1111, please pay the bootcamp fee", "card number"),
    ("My OpenDoor password is Grace2024!, why can't I log in?", "PIN or password"),
    ("password: hunter22", "PIN or password"),
    ("My OTP is 482913", "OTP code"),
]

SAFE_MESSAGES = [
    "Can you build a chatbot for my law firm?",
    "How much does a church website cost?",
    "My church needs help with tithe records",
    "I'm frustrated, my login doesn't work",
    "Maakye! Ɛte sɛn? Mepɛ sɛ mesua web development.",
    "My name is Test Person, call me on 0241234567",   # phone numbers must pass: save_lead needs them
    "My number is +233 24 123 4567",
    "I forgot my password, how do I reset it?",          # mentions a password but shares none
]


@pytest.mark.parametrize("message, expected", SENSITIVE_MESSAGES)
def test_sensitive_data_is_found(message, expected):
    assert find_sensitive_data(message) == expected


@pytest.mark.parametrize("message", SAFE_MESSAGES)
def test_normal_messages_have_no_sensitive_data(message):
    assert find_sensitive_data(message) is None


def test_sensitive_guardrail_trips_with_reason():
    output = run_input_guardrail("My MoMo PIN is 4821")
    assert output.tripwire_triggered is True
    assert output.output_info["reason"] == "sensitive_data"


def test_sensitive_guardrail_passes_normal_message():
    assert run_input_guardrail("When does the web dev bootcamp start?").tripwire_triggered is False


def test_only_the_latest_user_message_is_checked():
    # A PIN earlier in the conversation must not block every later message
    history = [
        {"role": "user", "content": "My PIN is 4821"},
        {"role": "assistant", "content": "Please don't share your PIN."},
        {"role": "user", "content": "Sorry. When does the bootcamp start?"},
    ]
    assert last_user_message(history) == "Sorry. When does the bootcamp start?"
    assert run_input_guardrail(history).tripwire_triggered is False


# ---------------------------------------------------------------------------
# Prices and dates (output)
# ---------------------------------------------------------------------------

def test_approved_data_comes_from_courses_table():
    assert 3500.0 in approved_prices()     # web_dev_bootcamp fee in tests/fixtures.py
    assert (1, 18) in approved_dates()     # web_dev_bootcamp start 2027-01-18
    assert (11, 5) in approved_dates()     # registration date 5 November 2025 (always allowed)


def test_price_check_follows_database_changes(test_db):
    # Before: GHS 4,000 is not approved
    assert find_unapproved("The fee is GHS 4,000.")["reason"] == "unapproved_price"

    # Change the fee and add a deadline and payment options in the database
    with Session(test_db) as session:
        course = session.exec(select(Course).where(Course.slug == "uxui_masterclass")).one()
        course.fee_ghs = 4000
        course.application_deadline = dt.date(2027, 2, 10)
        course.payment_options = "2 instalments of GHS 2,100"
        session.add(course)
        session.commit()

    # After: the new values pass straight away, no restart needed
    assert find_unapproved("The fee is GHS 4,000.") is None
    assert find_unapproved("Or pay 2 instalments of GHS 2,100.") is None
    assert find_unapproved("Apply by 10 February 2027.") is None


def test_with_no_courses_every_price_is_unapproved(test_db):
    with Session(test_db) as session:
        for course in session.exec(select(Course)).all():
            session.delete(course)
        session.commit()
    assert find_unapproved("The fee is GHS 3,500.")["reason"] == "unapproved_price"


@pytest.mark.parametrize("reply, reason", [
    ("The bootcamp costs GHS 1,500 and starts on 18 January.", "unapproved_price"),
    ("It is only 2,000 cedis.", "unapproved_price"),
    ("The fee is GH₵500.", "unapproved_price"),
    ("The bootcamp starts on 5 January.", "unapproved_date"),
    ("Classes begin March 3rd.", "unapproved_date"),
    ("Next intake: 2027-02-01.", "unapproved_date"),
])
def test_unapproved_price_or_date_is_found(reply, reason):
    assert find_unapproved(reply)["reason"] == reason


@pytest.mark.parametrize("reply", [
    "The Complete Web Development Bootcamp starts on 18 January 2027 and the fee is GHS 3,500.",
    "It starts on January 18th and costs 3,500 cedis.",
    "Fees for the next intake aren't confirmed yet, but I can register your interest.",
    "Pricing is shared after a short consultation.",
    "You can reach Coltek on +233 54 936 1771 from 9:00 to 18:00.",
    "The bootcamp runs for 12 weeks with 6 seats left.",
    "May I have your name and phone number?",
])
def test_approved_or_price_free_replies_pass(reply):
    assert find_unapproved(reply) is None


def test_price_guardrail_trips_with_reason():
    output = run_output_guardrail("The bootcamp costs GHS 1,500.")
    assert output.tripwire_triggered is True
    assert output.output_info["reason"] == "unapproved_price"


def test_price_guardrail_passes_approved_reply():
    assert run_output_guardrail("The fee is GHS 3,500.").tripwire_triggered is False


# ---------------------------------------------------------------------------
# Fallbacks
# ---------------------------------------------------------------------------

def test_every_block_reason_has_a_fallback():
    reasons = ["off_topic", "abusive", "injection", "sensitive_data",
               "unapproved_price", "unapproved_date",
               "promise", "legal_advice", "leaked_instructions", "wrong_company", "asked_for_secret"]
    for reason in reasons:
        assert FALLBACKS.get(reason), f"no fallback for {reason}"
