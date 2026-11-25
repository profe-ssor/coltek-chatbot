"""The logic behind POST /api/chat: run the agents for one visitor message and stream SSE events.

Agents SDK names used here were checked against openai-agents 0.25.0:
  Runner.run_streamed(...).stream_events() yields
    AgentUpdatedStreamEvent   type "agent_updated_stream_event", .new_agent        -> our "agent" event
    RunItemStreamEvent        type "run_item_stream_event", .name "tool_called",   -> our "status" event
                              .item = ToolCallItem (raw_item.name, or raw_item.type for hosted tools)
    RawResponsesStreamEvent   type "raw_response_event", .data.type
                              "response.output_text.delta", .data.delta             -> our "delta" event
  InputGuardrailTripwireTriggered / OutputGuardrailTripwireTriggered (.guardrail_result)
  RunConfig(trace_include_sensitive_data=..., workflow_name=..., group_id=..., model=...)
  SQLAlchemySession: see server/sessions.py

SSE events (JSON in the data field):
  start {"thread_id"} | agent {"name"} | status {"text"} | delta {"text"} | reset {} |
  done {"message_id", "agent"} | error {"text"}   plus ": keep-alive" comments every 15 s.
"reset" is sent only when an output guardrail blocks a reply that was already partly streamed:
the widget must clear that bubble before the fallback text arrives.
"""
import asyncio
import contextlib
import json
import logging
import time
from typing import AsyncIterator

from agents import (
    Agent,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    Runner,
)
from agents.items import ToolCallItem

from chatbot.agents import (
    academy_agent,
    department_for,
    get_starting_agent,
    opendoor_agent,
    services_agent,
    triage_agent,
)
from chatbot.config import settings
from chatbot.db import utc_now
from chatbot.guardrails import DEFAULT_FALLBACK, FALLBACKS, get_reason
from server.context import RequestContext
from server.models import ChatMessage, ChatThread, save_turn
from server.sessions import count_items, get_agent_session, rewind_to

logger = logging.getLogger("coltek.chat")

KEEPALIVE_SECONDS = 15
ERROR_TEXT = "Something went wrong. Please try again or call +233 54 936 1771."

# The ONLY texts a "status" event may carry. Visitors never see tool names: every tool maps to
# one of these, and anything unknown (file search, new tools) gets the fallback.
STATUS_COURSE = "Checking course details..."
STATUS_SAVING = "Saving your details..."
STATUS_DEMO = "Booking your demo..."
STATUS_FALLBACK = "One moment..."
STATUS_TEXTS = (STATUS_COURSE, STATUS_SAVING, STATUS_DEMO, STATUS_FALLBACK)
TOOL_STATUS = {
    "check_course_intake": STATUS_COURSE,
    "save_lead": STATUS_SAVING,
    "request_opendoor_demo": STATUS_DEMO,
}
ACADEMY_STATUS = STATUS_COURSE


def status_text(tool: str) -> str:
    return TOOL_STATUS.get(tool, STATUS_FALLBACK)

# Short agent names shown in the widget ("agent" and "done" events)
AGENT_DISPLAY = {
    triage_agent.name: "Coltek Assistant",
    services_agent.name: "Services",
    academy_agent.name: "Academy",
    opendoor_agent.name: "OpenDoor",
}

# Tests set this to a fake Model so no API calls are made; always None in production.
MODEL_OVERRIDE = None


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


KEEPALIVE = ": keep-alive\n\n"


def display_name(agent: Agent | None) -> str:
    return AGENT_DISPLAY.get(agent.name, agent.name) if agent else "Coltek Assistant"


def choose_starting_agent(thread: ChatThread, page: str | None) -> Agent:
    """1. The agent that replied last. 2. Academy page -> Academy, open-door.site -> OpenDoor. 3. Triage."""
    if thread.last_agent:
        return get_starting_agent(thread.last_agent)
    page = (page or "").lower()
    if "academy" in page:
        return academy_agent
    if "open-door.site" in page:
        return opendoor_agent
    return triage_agent


def tool_name(item: ToolCallItem) -> str:
    raw = item.raw_item
    name = raw.get("name") if isinstance(raw, dict) else getattr(raw, "name", None)
    kind = raw.get("type") if isinstance(raw, dict) else getattr(raw, "type", None)
    return name or kind or "unknown"


def tools_called(result) -> list[str]:
    """Tool NAMES only. Tool arguments (names, phone numbers) must never reach the logs."""
    return [tool_name(item) for item in (getattr(result, "new_items", None) or []) if isinstance(item, ToolCallItem)]


def make_run_config(thread_id: str) -> RunConfig:
    return RunConfig(
        workflow_name="Coltek chat",
        group_id=thread_id,                                          # groups a thread's runs in the traces
        trace_include_sensitive_data=settings.trace_include_sensitive_data,
        model=MODEL_OVERRIDE,
    )


async def replay_turn(thread: ChatThread, reply: ChatMessage) -> AsyncIterator[str]:
    """A retry of a message we already answered: send the saved reply again, run nothing."""
    yield sse("start", {"thread_id": thread.id})
    yield sse("delta", {"text": reply.content})
    yield sse("done", {"message_id": reply.id, "agent": AGENT_DISPLAY.get(reply.agent, reply.agent or "Coltek Assistant")})


async def stream_chat(thread: ChatThread, request: RequestContext, message: str,
                      client_message_id: str) -> AsyncIterator[str]:
    """Run one turn in a background task and yield its SSE events, with keep-alives while it works."""
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    task = asyncio.create_task(_run_turn(thread, request, message, client_message_id, queue))
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield KEEPALIVE                       # keeps proxies from closing a quiet connection
                continue
            if item is None:
                break
            yield item
    finally:
        if not task.done():                           # the visitor closed the connection
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


async def _run_turn(thread: ChatThread, request: RequestContext, message: str, client_message_id: str,
                    queue: asyncio.Queue) -> None:
    emit = queue.put_nowait
    started = time.perf_counter()
    received_at = utc_now()
    start_agent = choose_starting_agent(thread, request.page)
    log = {"thread_id": thread.id, "visitor_id": request.visitor_id, "start_agent": start_agent.name,
           "final_agent": None, "tools": [], "guardrail": None, "streamed": None, "duration_ms": None}
    result = None
    streamed_text: list[str] = []

    session = get_agent_session(thread.id)
    items_before = await count_items(session)          # to rewind the session if the turn is blocked
    run_context = request.to_run_context(thread.id)
    run_config = make_run_config(thread.id)

    emit(sse("start", {"thread_id": thread.id}))
    try:
        if start_agent is academy_agent:
            # WHY THE ACADEMY ADVISOR IS NOT STREAMED:
            # Output guardrails (the price/date check and the output checker) only run on the
            # FINISHED answer. If we streamed, the visitor would watch the words appear, so an
            # invented fee or start date would be on their screen before the guardrail could stop
            # it. The Academy advisor talks about fees and dates most, so we wait until every output
            # guardrail has passed and then send the whole reply as one "delta".
            log["streamed"] = False
            emit(sse("status", {"text": ACADEMY_STATUS}))
            result = await Runner.run(start_agent, message, session=session, context=run_context, run_config=run_config)
            reply = str(result.final_output)
            if result.last_agent is not start_agent:
                emit(sse("agent", {"name": display_name(result.last_agent)}))
            emit(sse("delta", {"text": reply}))
        else:
            log["streamed"] = True
            result = Runner.run_streamed(start_agent, message, session=session, context=run_context, run_config=run_config)
            current_agent = start_agent
            async for event in result.stream_events():
                if event.type == "agent_updated_stream_event":
                    if event.new_agent is not current_agent:                       # a handoff
                        current_agent = event.new_agent
                        emit(sse("agent", {"name": display_name(current_agent)}))
                elif event.type == "run_item_stream_event" and event.name == "tool_called":
                    emit(sse("status", {"text": status_text(tool_name(event.item))}))
                elif event.type == "raw_response_event" and getattr(event.data, "type", "") == "response.output_text.delta":
                    streamed_text.append(event.data.delta)
                    emit(sse("delta", {"text": event.data.delta}))
            reply = "".join(streamed_text) or str(result.final_output)

        # Success: save what the visitor typed and saw, and who replied
        final_agent = result.last_agent
        assistant = ChatMessage(thread_id=thread.id, role="assistant", content=reply, agent=final_agent.name)
        await asyncio.to_thread(
            save_turn, thread.id,
            [ChatMessage(thread_id=thread.id, role="user", content=message, created_at=received_at,
                         client_message_id=client_message_id), assistant],
            last_agent=final_agent.name, department=department_for(final_agent.name),
        )
        log["final_agent"] = final_agent.name
        emit(sse("done", {"message_id": assistant.id, "agent": display_name(final_agent)}))

    except InputGuardrailTripwireTriggered as e:
        # The SDK already saved the blocked message to the session: remove it, and never store the
        # typed text in chat_messages either. A placeholder shows something was blocked.
        guardrail = e.guardrail_result.guardrail.get_name()
        reason = get_reason(e.guardrail_result.output.output_info)
        log["guardrail"] = f"{guardrail}:{reason}"
        fallback = FALLBACKS.get(reason, DEFAULT_FALLBACK)
        placeholder = f"[message blocked: {reason}]"
        await rewind_to(session, items_before)
        await session.add_items([{"role": "user", "content": placeholder}, {"role": "assistant", "content": fallback}])
        assistant = ChatMessage(thread_id=thread.id, role="assistant", content=fallback, blocked_reason=reason)
        await asyncio.to_thread(
            save_turn, thread.id,
            [ChatMessage(thread_id=thread.id, role="user", content=placeholder, blocked_reason=reason,
                         created_at=received_at, client_message_id=client_message_id), assistant],
            guardrail_flag=reason,
        )
        emit(sse("delta", {"text": fallback}))
        emit(sse("done", {"message_id": assistant.id, "agent": display_name(start_agent)}))

    except OutputGuardrailTripwireTriggered as e:
        # The turn may have added several items (user message, tool calls, tool results, the bad
        # reply). Remove them all, then keep the visitor's (safe) message and our fallback.
        guardrail = e.guardrail_result.guardrail.get_name()
        reason = get_reason(e.guardrail_result.output.output_info)
        log["guardrail"] = f"{guardrail}:{reason}"
        blocked_agent = e.guardrail_result.agent
        fallback = FALLBACKS.get(reason, DEFAULT_FALLBACK)
        await rewind_to(session, items_before)
        await session.add_items([{"role": "user", "content": message}, {"role": "assistant", "content": fallback}])
        assistant = ChatMessage(thread_id=thread.id, role="assistant", content=fallback,
                                agent=blocked_agent.name, blocked_reason=reason)
        await asyncio.to_thread(
            save_turn, thread.id,
            [ChatMessage(thread_id=thread.id, role="user", content=message, created_at=received_at,
                         client_message_id=client_message_id), assistant],
            last_agent=blocked_agent.name, department=department_for(blocked_agent.name), guardrail_flag=reason,
        )
        log["final_agent"] = blocked_agent.name
        if streamed_text:
            emit(sse("reset", {}))                     # clear the partly streamed (blocked) reply
        emit(sse("delta", {"text": fallback}))
        emit(sse("done", {"message_id": assistant.id, "agent": display_name(blocked_agent)}))

    except asyncio.CancelledError:
        log["guardrail"] = "cancelled"
        with contextlib.suppress(Exception):
            await rewind_to(session, items_before)     # don't leave half a turn in the agent's memory
        raise

    except Exception as error:
        log["guardrail"] = "error"
        # Exception messages can quote tool arguments (names, phone numbers), so only the error type
        # is logged. The full traceback is added only in debug mode (TRACE_INCLUDE_SENSITIVE_DATA=true).
        logger.error("chat run failed thread=%s visitor=%s error=%s", thread.id, request.visitor_id,
                     type(error).__name__, exc_info=settings.trace_include_sensitive_data)
        with contextlib.suppress(Exception):
            await rewind_to(session, items_before)
        emit(sse("error", {"text": ERROR_TEXT}))

    finally:
        log["tools"] = tools_called(result)
        log["duration_ms"] = round((time.perf_counter() - started) * 1000)
        logger.info("chat_run %s", json.dumps(log))     # ids, agent names, tool names: never message text
        queue.put_nowait(None)
