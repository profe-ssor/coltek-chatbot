"""FastAPI chat API for the Coltek widget.

  POST /api/threads                      {page}                    -> {thread_id}
  GET  /api/threads/{thread_id}/messages                           -> {messages: [...]}   (404 if not yours)
  POST /api/chat                         {thread_id, message, page} -> text/event-stream (see chat_service.py)
  GET  /health                                                     -> {status: "ok"}

Run locally:  uvicorn server.main:app --reload --port 8000
"""
import asyncio
import logging
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from chatbot.config import settings
from server import chat_service
from server.context import RequestContext
from server.models import (create_tables, create_thread, find_saved_turn, get_thread,
                           get_visitor_thread, list_messages, list_threads)
from server.rate_limit import RateLimiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("coltek.server")

VISITOR_COOKIE = "coltek_vid"
VISITOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365          # one year
PAGE_HEADER = "X-Coltek-Page"
MAX_PAGE_LENGTH = 500
MAX_MESSAGE_LENGTH = 2000
HTML_TAG = re.compile(r"<[^>]*>")

RATE_LIMIT_TEXT = ("You've sent a lot of messages in a short time. Please wait a little and try again, "
                   "or call +233 54 936 1771.")
BUSY_TEXT = "Please wait for the current reply to finish."

rate_limiter = RateLimiter(settings.rate_limit_per_hour)
_active_threads: set[str] = set()   # threads with a reply in progress (one reply at a time per thread)
admin_basic = HTTPBasic(auto_error=False)


def require_admin(credentials: HTTPBasicCredentials | None = Depends(admin_basic)) -> str:
    """Fail closed: admin routes stay unavailable until credentials are configured."""
    if not settings.admin_username or not settings.admin_password:
        raise HTTPException(status_code=404, detail="Not found")
    valid = credentials is not None
    if valid:
        valid = secrets.compare_digest(credentials.username.encode(), settings.admin_username.encode())
        valid = secrets.compare_digest(credentials.password.encode(), settings.admin_password.encode()) and valid
    if not valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials.username


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def check_required_settings() -> None:
    """Fail loudly at startup instead of on the first visitor's message."""
    missing = []
    if not settings.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not settings.vector_store_id:
        missing.append("VECTOR_STORE_ID")
    if missing:
        raise RuntimeError(f"Missing required settings in .env: {', '.join(missing)}. The server will not start.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_required_settings()
    create_tables()
    logger.info("Coltek chat API ready (env=%s, origins=%s, traces include sensitive data=%s)",
                settings.app_env, settings.allowed_origins_list, settings.trace_include_sensitive_data)
    yield


app = FastAPI(title="Coltek Chat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,   # exact origins: required when credentials are allowed
    allow_credentials=True,                         # so the browser sends the visitor cookie
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", PAGE_HEADER],
)


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------

def get_visitor_id(request: Request) -> str:
    """The visitor ID from our cookie, or a new random one. Cookie values we didn't create are ignored."""
    value = request.cookies.get(VISITOR_COOKIE, "")
    if VISITOR_ID_PATTERN.match(value):
        return value
    return "v_" + secrets.token_urlsafe(24)


def clean_page(page: str | None) -> str | None:
    if not page:
        return None
    page = page.strip()[:MAX_PAGE_LENGTH]
    return page or None


def get_page(request: Request, body_page: str | None = None) -> str | None:
    """The page the chat is on: the request body, else the X-Coltek-Page header, else ?page=."""
    return clean_page(body_page or request.headers.get(PAGE_HEADER) or request.query_params.get("page"))


def get_client_ip(request: Request) -> str | None:
    """The visitor's IP. X-Forwarded-For is only believed when the request came from our own proxy.

    Nginx (proxy_add_x_forwarded_for) appends the address it saw to the END of the header,
    so the last entry is the one our proxy vouches for; earlier entries can be forged by the client.
    """
    peer = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if peer in settings.trusted_proxy_ips_list and forwarded:
        return forwarded.split(",")[-1].strip() or peer
    return peer


def set_visitor_cookie(response: Response, visitor_id: str) -> None:
    """httpOnly visitor cookie.

    Production: Secure + SameSite=None, so it is sent when the widget runs on our other domains.
    Development (http://localhost): browsers reject SameSite=None without Secure, so we use Lax;
    localhost:5500 and localhost:8000 are the same *site* (ports don't count), so Lax is still sent.
    """
    response.set_cookie(
        VISITOR_COOKIE, visitor_id, max_age=VISITOR_COOKIE_MAX_AGE, httponly=True,
        secure=settings.is_production, samesite="none" if settings.is_production else "lax", path="/",
    )


def clean_message(text: str) -> str:
    """Strip HTML tags and surrounding whitespace."""
    return HTML_TAG.sub("", text).strip()


def error(status: int, text: str, visitor_id: str | None = None, **extra) -> JSONResponse:
    response = JSONResponse({"error": text, **extra}, status_code=status)
    if visitor_id:
        set_visitor_cookie(response, visitor_id)
    return response


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class NewThreadBody(BaseModel):
    page: str | None = Field(default=None, max_length=5000)


class ChatBody(BaseModel):
    thread_id: str = Field(max_length=100)
    message: str = Field(max_length=20000)          # hard cap on payload; the real limit is checked below
    page: str | None = Field(default=None, max_length=5000)
    # A uuid the widget creates per message. Sending the same one again (Retry) returns the saved
    # reply instead of running the agent again, so a retry never duplicates messages or leads.
    client_message_id: str = Field(pattern=r"^[0-9a-fA-F-]{32,36}$")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/api/threads")
async def new_thread(body: NewThreadBody, request: Request) -> JSONResponse:
    visitor_id = get_visitor_id(request)
    thread = await asyncio.to_thread(create_thread, visitor_id, get_page(request, body.page))
    response = JSONResponse({"thread_id": thread.id})
    set_visitor_cookie(response, visitor_id)
    return response


@app.get("/api/threads/{thread_id}/messages")
async def thread_messages(thread_id: str, request: Request) -> JSONResponse:
    visitor_id = get_visitor_id(request)
    thread = await asyncio.to_thread(get_visitor_thread, thread_id, visitor_id)
    if thread is None:
        return error(404, "Conversation not found.", visitor_id)
    messages = await asyncio.to_thread(list_messages, thread_id)
    response = JSONResponse({
        "thread_id": thread_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "agent": chat_service.AGENT_DISPLAY.get(m.agent, m.agent) if m.agent else None,
                "blocked": m.blocked_reason is not None,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    })
    set_visitor_cookie(response, visitor_id)
    return response


@app.post("/api/chat")
async def chat(body: ChatBody, request: Request) -> Response:
    visitor_id = get_visitor_id(request)

    message = clean_message(body.message)
    if not message:
        return error(422, "Please type a message.", visitor_id)
    if len(message) > MAX_MESSAGE_LENGTH:
        return error(422, f"Please keep your message under {MAX_MESSAGE_LENGTH} characters.", visitor_id)

    thread = await asyncio.to_thread(get_visitor_thread, body.thread_id, visitor_id)
    if thread is None:
        return error(404, "Conversation not found.", visitor_id)

    # Retry of a message we already have? Replay the saved reply (no agent run, no rate-limit hit).
    client_message_id = body.client_message_id.lower()
    saved_user, saved_reply = await asyncio.to_thread(find_saved_turn, thread.id, client_message_id)
    if saved_user is not None:
        if saved_reply is None or thread.id in _active_threads:
            return error(409, BUSY_TEXT, visitor_id)
        response = StreamingResponse(chat_service.replay_turn(thread, saved_reply), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        set_visitor_cookie(response, visitor_id)
        return response

    wait = rate_limiter.hit(visitor_id, get_client_ip(request))
    if wait:
        response = error(429, RATE_LIMIT_TEXT, visitor_id, retry_after=wait)
        response.headers["Retry-After"] = str(wait)
        return response

    if thread.id in _active_threads:
        return error(409, BUSY_TEXT, visitor_id)
    _active_threads.add(thread.id)

    context = RequestContext(visitor_id=visitor_id, page=get_page(request, body.page), ip=get_client_ip(request))

    async def events():
        try:
            async for chunk in chat_service.stream_chat(thread, context, message, client_message_id):
                yield chunk
        finally:
            _active_threads.discard(thread.id)

    response = StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},   # no buffering in Nginx
    )
    set_visitor_cookie(response, visitor_id)
    return response


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(_admin: str = Depends(require_admin)) -> HTMLResponse:
    html = Path(__file__).with_name("admin.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/admin/api/conversations")
async def admin_conversations(_admin: str = Depends(require_admin)) -> JSONResponse:
    threads = await asyncio.to_thread(list_threads, 100, 0)
    conversations = []
    for thread in threads:
        messages = await asyncio.to_thread(list_messages, thread.id)
        conversations.append({
            "id": thread.id,
            "page": thread.page,
            "department": thread.department,
            "updated_at": thread.updated_at.isoformat(),
            "last_message": messages[-1].content[:240] if messages else "",
        })
    return JSONResponse({"conversations": conversations}, headers={"Cache-Control": "no-store"})


@app.get("/admin/api/conversations/{thread_id}")
async def admin_conversation(thread_id: str, _admin: str = Depends(require_admin)) -> JSONResponse:
    thread = await asyncio.to_thread(get_thread, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await asyncio.to_thread(list_messages, thread_id)
    return JSONResponse({
        "id": thread.id,
        "page": thread.page,
        "department": thread.department,
        "messages": [{
            "role": message.role,
            "content": message.content,
            "agent": chat_service.AGENT_DISPLAY.get(message.agent, message.agent) if message.agent else None,
            "blocked": message.blocked_reason is not None,
            "created_at": message.created_at.isoformat(),
        } for message in messages],
    }, headers={"Cache-Control": "no-store"})
