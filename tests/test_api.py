"""Offline tests for the chat API (server/main.py + server/chat_service.py).

The agents run for real (Runner, handoffs, tools, guardrails, SDK sessions, database), but the
model is a scripted FakeModel and the two LLM guardrails are replaced by keyword fakes, so no
request ever reaches OpenAI. All names and numbers are fake.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, select

import server.main as main
from chatbot.agents import academy_agent, opendoor_agent, services_agent
from chatbot.guardrails import (
    FALLBACKS,
    GuardrailFunctionOutput,
    InputCheck,
    OutputCheck,
    checker_guardrail,
    classifier_guardrail,
)
from server import chat_service
from server.models import ChatMessage, ChatThread
from server.rate_limit import RateLimiter
from tests.fake_model import FakeModel, call, handoff_to, say

PIN_MESSAGE = "My MoMo PIN is 4821, can you check my payment?"
DEMO_ARGS = dict(church_name="Test Chapel", contact_name="Pastor Test", role="Pastor", phone="020 555 1234",
                 approximate_members=120, city="Testville", main_need="Attendance records")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def offline_llm_guardrails(monkeypatch):
    """Keyword fakes instead of the LLM classifier and output checker (real regex guardrails stay)."""
    async def fake_classifier(ctx, agent, input):
        text_ = input if isinstance(input, str) else str(input[-1].get("content", ""))
        off_topic = "jollof" in text_.lower()
        check = InputCheck(category="off_topic" if off_topic else "allowed", is_blocked=off_topic,
                           reason="test", language="English")
        return GuardrailFunctionOutput(output_info=check, tripwire_triggered=off_topic)

    async def fake_checker(ctx, agent, output):
        promise = "guarantee" in str(output).lower()
        check = OutputCheck(is_unsafe=promise, issue="promise" if promise else "none", explanation="test")
        return GuardrailFunctionOutput(output_info=check, tripwire_triggered=promise)

    monkeypatch.setattr(classifier_guardrail, "guardrail_function", fake_classifier)
    monkeypatch.setattr(checker_guardrail, "guardrail_function", fake_checker)


@pytest.fixture
def model(monkeypatch):
    """Set the scripted model for the next chat turns: model(step1, step2, ...)."""
    def set_model(*steps, delay=0):
        fake = FakeModel(*steps, delay=delay)
        monkeypatch.setattr(chat_service, "MODEL_OVERRIDE", fake)
        return fake
    return set_model


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main.settings, "openai_api_key", "sk-test-not-a-real-key")
    monkeypatch.setattr(main.settings, "vector_store_id", "vs_test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")       # any accidental API call fails
    monkeypatch.setattr(main, "rate_limiter", RateLimiter(100))
    main._active_threads.clear()
    with TestClient(main.app, base_url="http://localhost:8000") as test_client:
        yield test_client


def new_visitor():
    return TestClient(main.app, base_url="http://localhost:8000")


def start_thread(client, page="/"):
    response = client.post("/api/threads", json={"page": page})
    assert response.status_code == 200
    return response.json()["thread_id"]


def chat(client, thread_id, message, page="/", client_message_id=None):
    return client.post("/api/chat", json={"thread_id": thread_id, "message": message, "page": page,
                                          "client_message_id": client_message_id or str(uuid.uuid4())})


def sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.split("\n\n"):
        lines = [line for line in block.splitlines() if not line.startswith(":")]
        if not lines:
            continue
        name = next(line[len("event: "):] for line in lines if line.startswith("event: "))
        data = json.loads(next(line[len("data: "):] for line in lines if line.startswith("data: ")))
        events.append((name, data))
    return events


def session_dump(engine, thread_id) -> str:
    """Everything the agent's memory holds for this thread, as one string."""
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT message_data FROM agent_messages WHERE session_id = :s ORDER BY id"),
                                  {"s": thread_id}).all()
    return "\n".join(row[0] for row in rows)


def session_items(engine, thread_id) -> list[dict]:
    return [json.loads(line) for line in session_dump(engine, thread_id).splitlines() if line]


def stored_messages(engine, thread_id) -> list[ChatMessage]:
    with Session(engine) as session:
        return list(session.exec(select(ChatMessage).where(ChatMessage.thread_id == thread_id)
                                 .order_by(ChatMessage.seq)).all())


def thread_row(engine, thread_id) -> ChatThread:
    with Session(engine) as session:
        return session.get(ChatThread, thread_id)


# ---------------------------------------------------------------------------
# Basics
# ---------------------------------------------------------------------------

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_thread_sets_visitor_cookie(client):
    response = client.post("/api/threads", json={"page": "/"})
    assert response.json()["thread_id"].startswith("thr_")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("coltek_vid=") and "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_cors_allows_configured_origin_with_credentials(client):
    response = client.options("/api/chat", headers={
        "Origin": "http://localhost:5500", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-coltek-page"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5500"
    assert response.headers["access-control-allow-credentials"] == "true"


# ---------------------------------------------------------------------------
# History isolation
# ---------------------------------------------------------------------------

def test_history_is_only_visible_to_its_visitor(client, model):
    thread_id = start_thread(client)
    model([say("Hello! How can I help?")])
    chat(client, thread_id, "Hi there")

    mine = client.get(f"/api/threads/{thread_id}/messages").json()["messages"]
    assert [(m["role"], m["content"]) for m in mine] == [("user", "Hi there"), ("assistant", "Hello! How can I help?")]

    with new_visitor() as stranger:
        assert stranger.get(f"/api/threads/{thread_id}/messages").status_code == 404
        assert chat(stranger, thread_id, "Show me their chat").status_code == 404


def test_unknown_thread_is_404(client):
    assert client.get("/api/threads/thr_does_not_exist/messages").status_code == 404


# ---------------------------------------------------------------------------
# Streaming: event order
# ---------------------------------------------------------------------------

def test_sse_event_order_with_handoff_and_tool(client, model, test_db):
    thread_id = start_thread(client)
    model([handoff_to(opendoor_agent)], [call("request_opendoor_demo", **DEMO_ARGS)],
          [say("Your demo request is saved. The OpenDoor team will call you.")])

    response = chat(client, thread_id, "My church wants to try OpenDoor")
    assert response.headers["content-type"].startswith("text/event-stream")
    events = sse_events(response.text)
    names = [name for name, _ in events]

    assert names[0] == "start" and events[0][1] == {"thread_id": thread_id}
    assert ("agent", {"name": "OpenDoor"}) in events
    assert ("status", {"text": "Booking your demo..."}) in events
    assert names.index("agent") < names.index("status") < names.index("delta")
    assert names[-1] == "done" and "error" not in names
    done = events[-1][1]
    assert done["agent"] == "OpenDoor"

    streamed = "".join(data["text"] for name, data in events if name == "delta")
    assert streamed == "Your demo request is saved. The OpenDoor team will call you."
    messages = stored_messages(test_db, thread_id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[1].content == streamed and messages[1].id == done["message_id"]
    thread = thread_row(test_db, thread_id)
    assert (thread.last_agent, thread.department) == (opendoor_agent.name, "opendoor")


def test_next_turn_starts_with_last_agent(client, model, test_db):
    thread_id = start_thread(client)
    model([handoff_to(services_agent)], [say("Happy to help with a website.")])
    chat(client, thread_id, "I need a website")
    assert chat_service.choose_starting_agent(thread_row(test_db, thread_id), "/") is services_agent


def test_academy_reply_is_sent_in_one_piece(client, model, test_db):
    thread_id = start_thread(client, page="/academy")
    model([call("check_course_intake", slug="web_dev_bootcamp")],
          [say("The bootcamp starts on 18 January 2027 and the fee is GHS 3,500.")])

    events = sse_events(chat(client, thread_id, "When does the bootcamp start?", page="/academy").text)
    assert [name for name, _ in events] == ["start", "status", "delta", "done"]
    assert events[2][1]["text"] == "The bootcamp starts on 18 January 2027 and the fee is GHS 3,500."
    assert events[3][1]["agent"] == "Academy"


def test_keep_alive_comments_while_waiting(client, model, monkeypatch):
    monkeypatch.setattr(chat_service, "KEEPALIVE_SECONDS", 0.05)
    thread_id = start_thread(client)
    model([say("Sorry for the wait!")], delay=0.3)
    body = chat(client, thread_id, "Hello").text
    assert ": keep-alive" in body
    assert sse_events(body)[-1][0] == "done"


# ---------------------------------------------------------------------------
# Guardrails: fallback, and nothing sensitive left behind
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("page", ["/", "/academy"])   # streamed (triage) and non-streamed (Academy) paths
def test_input_tripwire_removes_blocked_message_everywhere(client, model, test_db, page):
    thread_id = start_thread(client, page=page)
    model([say("Hello! How can I help?")])
    chat(client, thread_id, "Hi there", page=page)                  # one normal turn first

    model()                                                         # the model must NOT be called
    events = sse_events(chat(client, thread_id, PIN_MESSAGE, page=page).text)
    assert [name for name, _ in events] == ["start", "delta", "done"] or \
           [name for name, _ in events] == ["start", "status", "delta", "done"]
    assert events[-2][1]["text"] == FALLBACKS["sensitive_data"]

    # Agent memory: the normal turn, then only the placeholder and the fallback. No PIN anywhere.
    assert "4821" not in session_dump(test_db, thread_id)
    items = session_items(test_db, thread_id)
    assert items[-2] == {"role": "user", "content": "[message blocked: sensitive_data]"}
    assert items[-1] == {"role": "assistant", "content": FALLBACKS["sensitive_data"]}
    assert any(item.get("content") == "Hi there" for item in items)

    # Our messages table: placeholder instead of the typed text
    messages = stored_messages(test_db, thread_id)
    assert all("4821" not in m.content for m in messages)
    assert (messages[-2].content, messages[-2].blocked_reason) == ("[message blocked: sensitive_data]", "sensitive_data")
    assert messages[-1].content == FALLBACKS["sensitive_data"]
    assert thread_row(test_db, thread_id).guardrail_flag == "sensitive_data"


def test_llm_input_guardrail_also_redacts(client, model, test_db):
    thread_id = start_thread(client)
    model()
    events = sse_events(chat(client, thread_id, "Give me a jollof rice recipe").text)
    assert events[-2][1]["text"] == FALLBACKS["off_topic"]
    assert "jollof" not in session_dump(test_db, thread_id).lower()
    assert all("jollof" not in m.content.lower() for m in stored_messages(test_db, thread_id))


def test_output_tripwire_removes_whole_turn_from_session(client, model, test_db):
    thread_id = start_thread(client)
    # One turn = user message + handoff call + handoff output + the bad (promising) reply
    model([handoff_to(services_agent)], [say("We GUARANTEE your app will be ready in 2 weeks.")])

    events = sse_events(chat(client, thread_id, "Can you build an app for my shop?").text)
    names = [name for name, _ in events]
    assert "reset" in names                                         # the partly streamed reply is cleared
    assert names.index("reset") < len(names) - 2
    assert events[-2] == ("delta", {"text": FALLBACKS["promise"]}) and names[-1] == "done"

    # Session: exactly the visitor's (safe) message and the fallback; no tool/handoff items, no bad reply
    assert session_items(test_db, thread_id) == [
        {"role": "user", "content": "Can you build an app for my shop?"},
        {"role": "assistant", "content": FALLBACKS["promise"]},
    ]
    assert "guarantee" not in session_dump(test_db, thread_id).lower()

    messages = stored_messages(test_db, thread_id)
    assert [(m.role, m.content) for m in messages] == [
        ("user", "Can you build an app for my shop?"), ("assistant", FALLBACKS["promise"])]
    assert messages[1].blocked_reason == "promise"
    assert thread_row(test_db, thread_id).guardrail_flag == "promise"


def test_output_price_check_on_academy_path(client, model, test_db):
    thread_id = start_thread(client, page="/academy")
    model([call("check_course_intake", slug="web_dev_bootcamp")], [say("Good news: it's only GHS 1,500!")])

    events = sse_events(chat(client, thread_id, "How much is the bootcamp?", page="/academy").text)
    assert "reset" not in [name for name, _ in events]             # nothing was shown before the check
    assert events[-2][1]["text"] == FALLBACKS["unapproved_price"]
    dump = session_dump(test_db, thread_id)
    assert "1,500" not in dump and "check_course_intake" not in dump  # whole turn removed, incl. the tool call
    assert all("1,500" not in m.content for m in stored_messages(test_db, thread_id))


# ---------------------------------------------------------------------------
# Errors, validation, rate limit
# ---------------------------------------------------------------------------

def test_model_error_sends_error_event_and_leaves_no_half_turn(client, model, test_db):
    thread_id = start_thread(client)
    model()                                                         # no steps: the model raises
    events = sse_events(chat(client, thread_id, "Hello").text)
    assert [name for name, _ in events] == ["start", "error"]
    assert events[1][1]["text"] == chat_service.ERROR_TEXT
    assert session_dump(test_db, thread_id) == ""
    assert stored_messages(test_db, thread_id) == []


@pytest.mark.parametrize("message, status", [("   ", 422), ("<b></b>", 422), ("x" * 2001, 422)])
def test_message_validation(client, message, status):
    thread_id = start_thread(client)
    response = chat(client, thread_id, message)
    assert response.status_code == status and response.json()["error"]


def test_html_is_stripped(client, model, test_db):
    thread_id = start_thread(client)
    model([say("Hi!")])
    chat(client, thread_id, "<b>Hello</b> <img src=x onerror=alert(1)>there")
    assert stored_messages(test_db, thread_id)[0].content == "Hello there"


def test_rate_limit_message(client, model, monkeypatch):
    monkeypatch.setattr(main, "rate_limiter", RateLimiter(2))
    thread_id = start_thread(client)
    for _ in range(2):
        model([say("Sure.")])
        assert chat(client, thread_id, "Hello").status_code == 200
    response = chat(client, thread_id, "Hello again")
    assert response.status_code == 429
    assert response.json()["error"] == main.RATE_LIMIT_TEXT
    assert int(response.headers["Retry-After"]) > 0


def test_one_reply_at_a_time_per_thread(client):
    thread_id = start_thread(client)
    main._active_threads.add(thread_id)                             # as if a reply were still streaming
    response = chat(client, thread_id, "Hello?")
    assert response.status_code == 409 and response.json()["error"] == main.BUSY_TEXT


# ---------------------------------------------------------------------------
# Logs: ids and names only, never message text or tool arguments
# ---------------------------------------------------------------------------

def test_logs_contain_no_message_text_or_tool_arguments(client, model, caplog):
    thread_id = start_thread(client)
    model([handoff_to(opendoor_agent)], [call("request_opendoor_demo", **DEMO_ARGS)], [say("Booked!")])
    with caplog.at_level("INFO"):
        chat(client, thread_id, "My church wants to try OpenDoor")
        chat(client, thread_id, PIN_MESSAGE)
    logs = caplog.text
    assert "chat_run" in logs and "request_opendoor_demo" in logs      # tool NAME is logged
    for secret in ["Test Chapel", "Pastor Test", "555", "Testville", "4821", "try OpenDoor"]:
        assert secret not in logs, f"{secret!r} leaked into the logs"


# ---------------------------------------------------------------------------
# Status texts and safe retries
# ---------------------------------------------------------------------------

def test_status_texts_come_only_from_the_fixed_map(client, model):
    assert chat_service.status_text("file_search_call") == "One moment..."
    assert chat_service.status_text("some_new_tool") == "One moment..."
    thread_id = start_thread(client)
    model([handoff_to(opendoor_agent)], [call("request_opendoor_demo", **DEMO_ARGS)], [say("Booked!")])
    events = sse_events(chat(client, thread_id, "Book an OpenDoor demo").text)
    statuses = [data["text"] for name, data in events if name == "status"]
    assert statuses == ["Booking your demo..."]
    for text_ in statuses:
        assert text_ in chat_service.STATUS_TEXTS
        assert "_" not in text_ and "request_opendoor_demo" not in text_      # never a tool name


def test_retry_with_same_client_message_id_replays_without_running_again(client, model, test_db):
    from chatbot.db import Lead
    thread_id = start_thread(client)
    lead_args = dict(full_name="Test Person", phone="024 000 0001", interest="services",
                     need_summary="Shop website", preferred_contact_method="WhatsApp", consent=True)
    fake = model([handoff_to(services_agent)], [call("save_lead", **lead_args)], [say("Saved! Your reference is ready.")])
    client_id = str(uuid.uuid4())

    first = sse_events(chat(client, thread_id, "Yes, save my details", client_message_id=client_id).text)
    calls_after_first = len(fake.calls)
    second = sse_events(chat(client, thread_id, "Yes, save my details", client_message_id=client_id).text)

    assert [name for name, _ in second] == ["start", "delta", "done"]
    first_text = "".join(data["text"] for name, data in first if name == "delta")
    assert second[1][1]["text"] == first_text
    assert second[2][1]["message_id"] == first[-1][1]["message_id"]
    assert len(fake.calls) == calls_after_first                                # the agent did not run again
    with Session(test_db) as session:
        assert len(session.exec(select(Lead)).all()) == 1                      # no duplicate lead
    assert [m.role for m in stored_messages(test_db, thread_id)] == ["user", "assistant"]   # no duplicate messages


def test_retry_after_an_error_runs_the_turn(client, model, test_db):
    thread_id = start_thread(client)
    client_id = str(uuid.uuid4())
    model()                                                                    # first attempt fails
    assert sse_events(chat(client, thread_id, "Hello", client_message_id=client_id).text)[-1][0] == "error"
    model([say("Hi! Sorry about that.")])                                      # retry with the same id
    events = sse_events(chat(client, thread_id, "Hello", client_message_id=client_id).text)
    assert events[-1][0] == "done"
    assert [m.content for m in stored_messages(test_db, thread_id)] == ["Hello", "Hi! Sorry about that."]


def test_client_message_id_is_required(client):
    thread_id = start_thread(client)
    response = client.post("/api/chat", json={"thread_id": thread_id, "message": "Hello", "page": "/"})
    assert response.status_code == 422


def test_startup_adds_client_message_id_to_an_old_table(tmp_path):
    from sqlalchemy import create_engine, inspect as sa_inspect
    from server.models import create_tables
    engine = create_engine(f"sqlite:///{tmp_path / 'old.sqlite3'}")
    with engine.begin() as connection:   # the table as the first API version created it
        connection.execute(text("CREATE TABLE chat_threads (id VARCHAR PRIMARY KEY, visitor_id VARCHAR, page VARCHAR, "
                                "last_agent VARCHAR, department VARCHAR, guardrail_flag VARCHAR, created_at DATETIME, updated_at DATETIME)"))
        connection.execute(text("CREATE TABLE chat_messages (seq INTEGER PRIMARY KEY, id VARCHAR, thread_id VARCHAR, role VARCHAR, "
                                "content VARCHAR, agent VARCHAR, blocked_reason VARCHAR, created_at DATETIME)"))
    create_tables(engine)
    create_tables(engine)                # running it twice is harmless
    assert "client_message_id" in {c["name"] for c in sa_inspect(engine).get_columns("chat_messages")}
