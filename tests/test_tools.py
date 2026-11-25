"""Tests for chatbot.tools against a temporary SQLite database (no API calls).

The tools are called the same way the Agents SDK calls them: on_invoke_tool(ToolContext, json_args).
All people, churches and numbers are fake.
"""
import asyncio
import json
import logging

import pytest
from sqlmodel import Session, select

import chatbot.tools as tools
from chatbot import db, notify
from chatbot.context import ChatContext
from chatbot.db import Course, DemoRequest, Lead
from chatbot.tools import check_course_intake, normalise_ghana_phone, request_opendoor_demo, save_lead
from agents.tool_context import ToolContext


def call_tool(tool, args: dict, context=None):
    """Invoke a function tool like the SDK does, with an optional run context."""
    ctx = ToolContext(context=context, tool_name=tool.name, tool_call_id="test-call",
                      tool_arguments=json.dumps(args))
    result = asyncio.run(tool.on_invoke_tool(ctx, json.dumps(args)))
    assert isinstance(result, dict), f"tool raised an error instead of returning a dict: {result}"
    return result


@pytest.fixture
def sent_emails(monkeypatch):
    """Record notify_team calls instead of sending email."""
    calls = []
    monkeypatch.setattr(tools, "notify_team", lambda subject, body: calls.append((subject, body)) or True)
    return calls


LEAD = {
    "full_name": "Test Person",
    "phone": "024 123 4567",
    "interest": "academy",
    "need_summary": "Wants to join the web dev bootcamp",
    "preferred_contact_method": "WhatsApp",
    "consent": True,
}

DEMO = {
    "church_name": "Test Chapel",
    "contact_name": "Pastor Test",
    "role": "Senior Pastor",
    "phone": "020-555-1234",
    "approximate_members": 350,
    "city": "Accra",
    "main_need": "Attendance and giving records",
}


# ---------------------------------------------------------------------------
# Safety: tests use a temporary database
# ---------------------------------------------------------------------------

def test_tests_never_use_the_real_database():
    url = str(db.get_engine().url)
    assert "chatbot.sqlite3" not in url
    assert "test.sqlite3" in url


def test_model_cannot_set_visitor_id_or_source_page():
    for tool in (check_course_intake, save_lead, request_opendoor_demo):
        params = tool.params_json_schema["properties"]
        assert "ctx" not in params
        assert "visitor_id" not in params and "source_page" not in params


# ---------------------------------------------------------------------------
# check_course_intake
# ---------------------------------------------------------------------------

def test_course_details_come_from_the_database():
    result = call_tool(check_course_intake, {"slug": "web_dev_bootcamp"})
    assert result["status"] == "open"
    assert result["next_start_date"] == "2027-01-18"
    assert result["fee_ghs"] == 3500.0
    assert result["seats_left"] == 6


def test_unconfirmed_details_are_none():
    result = call_tool(check_course_intake, {"slug": "uxui_masterclass"})
    assert result["fee_ghs"] is None
    assert result["next_start_date"] is None
    assert result["status"] == "not_scheduled"


def test_missing_course_returns_error(test_db):
    with Session(test_db) as session:
        session.delete(session.exec(select(Course).where(Course.slug == "uxui_masterclass")).one())
        session.commit()
    assert call_tool(check_course_intake, {"slug": "uxui_masterclass"})["error"] == "COURSE_NOT_FOUND"


# ---------------------------------------------------------------------------
# save_lead
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("024 123 4567", "+233241234567"),
    ("024-123-4567", "+233241234567"),
    ("233241234567", "+233241234567"),
    ("+233 24 123 4567", "+233241234567"),
])
def test_ghana_phone_normalisation(raw, expected):
    assert normalise_ghana_phone(raw) == expected


def test_lead_without_consent_is_not_saved(test_db, sent_emails):
    result = call_tool(save_lead, {**LEAD, "consent": False})
    assert result["error"] == "CONSENT_REQUIRED"
    with Session(test_db) as session:
        assert session.exec(select(Lead)).all() == []
    assert sent_emails == []


def test_lead_is_saved_with_context_and_team_is_notified(test_db, sent_emails):
    context = ChatContext(visitor_id="visitor-test-1", source_page="/academy")
    result = call_tool(save_lead, LEAD, context=context)

    assert result["reference"] == "CT-L-000001"
    with Session(test_db) as session:
        lead = session.exec(select(Lead)).one()
    assert lead.phone == "+233241234567"            # E.164
    assert lead.visitor_id == "visitor-test-1"      # from the run context
    assert lead.source_page == "/academy"
    assert lead.consent is True and lead.consent_at is not None
    assert lead.status == "new"

    assert len(sent_emails) == 1
    assert "CT-L-000001" in sent_emails[0][0]


def test_duplicate_lead_returns_existing_reference(test_db, sent_emails):
    first = call_tool(save_lead, LEAD)
    second = call_tool(save_lead, {**LEAD, "phone": "+233 24 123 4567"})   # same number, other format
    assert second["error"] == "DUPLICATE_LEAD"
    assert first["reference"] in second["message"]
    assert len(sent_emails) == 1                    # no email for the duplicate


def test_same_phone_different_interest_is_a_new_lead(sent_emails):
    call_tool(save_lead, LEAD)
    result = call_tool(save_lead, {**LEAD, "interest": "services"})
    assert result["reference"] == "CT-L-000002"


def test_lead_works_without_context(test_db, sent_emails):
    # e.g. called from a notebook with no ChatContext
    call_tool(save_lead, LEAD, context=None)
    with Session(test_db) as session:
        assert session.exec(select(Lead)).one().visitor_id is None


# ---------------------------------------------------------------------------
# request_opendoor_demo
# ---------------------------------------------------------------------------

def test_demo_is_saved_and_team_is_notified(test_db, sent_emails):
    result = call_tool(request_opendoor_demo, DEMO, context=ChatContext(visitor_id="visitor-test-2"))
    assert result["reference"] == "CT-D-000001"
    with Session(test_db) as session:
        demo = session.exec(select(DemoRequest)).one()
    assert demo.phone == "+233205551234"
    assert demo.city_region == "Accra"
    assert demo.approx_members == 350
    assert demo.visitor_id == "visitor-test-2"
    assert demo.consent is True and demo.consent_at is not None
    assert len(sent_emails) == 1


def test_duplicate_demo_ignores_church_name_case(sent_emails):
    first = call_tool(request_opendoor_demo, DEMO)
    second = call_tool(request_opendoor_demo, {**DEMO, "church_name": "  test chapel "})
    assert second["error"] == "DUPLICATE_DEMO_REQUEST"
    assert first["reference"] in second["message"]


# ---------------------------------------------------------------------------
# notify_team
# ---------------------------------------------------------------------------

def test_notify_without_smtp_logs_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="chatbot.notify"):
        assert notify.notify_team("Test subject", "Test body") is False
    assert "SMTP not configured" in caplog.text


def test_notify_smtp_failure_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(notify.settings, "smtp_host", "smtp.invalid.test")
    monkeypatch.setattr(notify.settings, "notify_email_to", "team@example.com")

    def broken_smtp(*args, **kwargs):
        raise OSError("connection refused")
    monkeypatch.setattr(notify.smtplib, "SMTP", broken_smtp)

    with caplog.at_level(logging.WARNING, logger="chatbot.notify"):
        assert notify.notify_team("Test subject", "Test body") is False
    assert "Could not email the team" in caplog.text


def test_lead_is_saved_even_if_email_fails(test_db, monkeypatch):
    monkeypatch.setattr(notify.settings, "smtp_host", "smtp.invalid.test")
    monkeypatch.setattr(notify.settings, "notify_email_to", "team@example.com")
    monkeypatch.setattr(notify.smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))

    assert call_tool(save_lead, LEAD)["reference"] == "CT-L-000001"
