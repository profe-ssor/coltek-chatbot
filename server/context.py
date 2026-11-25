"""Per-request context built by the FastAPI endpoints, and the run context the agents' tools see."""
from dataclasses import dataclass


@dataclass
class RequestContext:
    visitor_id: str          # anonymous visitor ID from our httpOnly cookie; scopes every thread
    page: str | None = None  # the page the chat was opened on, e.g. "coltekacademy.coltektechnologies.io/courses"
    ip: str | None = None    # client IP, for rate limiting. Never sent to the model or the tools.

    def to_run_context(self, thread_id: str) -> "AgentRunContext":
        return AgentRunContext(visitor_id=self.visitor_id, source_page=self.page, thread_id=thread_id)


@dataclass
class AgentRunContext:
    """Passed as `context=` to Runner.run / run_streamed.

    The tools read visitor_id and source_page by attribute name (chatbot/context.py: context_values),
    so these field names must not change. No IP address here on purpose.
    """
    visitor_id: str
    source_page: str | None
    thread_id: str
