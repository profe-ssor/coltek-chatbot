"""The run context: details about the visitor that the server knows and the model must never set.

The server passes it to every run:
    await safe_run(agent, input, context=ChatContext(visitor_id="...", source_page="/academy"))
Tools read it through their first parameter `ctx: RunContextWrapper[ChatContext]`,
which the Agents SDK hides from the model (it is not part of the tool's JSON schema).
"""
from dataclasses import dataclass


@dataclass
class ChatContext:
    visitor_id: str | None = None     # anonymous ID from the website widget's visitor cookie
    source_page: str | None = None    # the page the chat was opened on, e.g. "/academy"


def context_values(ctx) -> tuple[str | None, str | None]:
    """(visitor_id, source_page) from a tool's ctx. Works when no context was passed (e.g. in a notebook).

    The context can be a ChatContext, a dict, any object with visitor_id/source_page attributes,
    or a wrapper object whose `request_context` has a `to_chat_context()` method. It is detected
    by shape, so chatbot/ never imports from server/.
    """
    context = getattr(ctx, "context", None)
    if context is None:
        return None, None
    inner = getattr(context, "request_context", None)
    if inner is not None and hasattr(inner, "to_chat_context"):
        context = inner.to_chat_context()
    if isinstance(context, dict):
        return context.get("visitor_id"), context.get("source_page")
    return getattr(context, "visitor_id", None), getattr(context, "source_page", None)
