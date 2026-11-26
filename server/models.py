"""Chat threads and the messages the visitor sees (same database as chatbot/db.py).

These tables are what GET /api/threads/{id}/messages shows. The agent's own memory (including
tool calls and their arguments) is kept separately in the Agents SDK session tables, see sessions.py.
Both contain personal data: include them in backups, deletion requests and retention clean-up.
"""
import datetime as dt
import secrets

from sqlalchemy import inspect, text
from sqlmodel import Field, Session, SQLModel, select

from chatbot.db import get_engine, utc_now


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


class ChatThread(SQLModel, table=True):
    __tablename__ = "chat_threads"

    id: str = Field(default_factory=lambda: new_id("thr"), primary_key=True)
    visitor_id: str = Field(index=True)
    page: str | None = None              # page the conversation started on
    last_agent: str | None = None        # agent that replied last; the next turn starts with it
    department: str | None = None        # general / services / academy / opendoor
    guardrail_flag: str | None = None    # last guardrail reason that blocked something in this thread
    created_at: dt.datetime = Field(default_factory=utc_now)
    updated_at: dt.datetime = Field(default_factory=utc_now)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    seq: int | None = Field(default=None, primary_key=True)        # insertion order
    id: str = Field(default_factory=lambda: new_id("msg"), unique=True, index=True)
    thread_id: str = Field(index=True, foreign_key="chat_threads.id")
    role: str                                                     # "user" or "assistant"
    content: str                                                  # a blocked user message is stored as a placeholder
    agent: str | None = None                                      # assistant messages: which agent replied
    blocked_reason: str | None = None                             # set when a guardrail replaced the content
    client_message_id: str | None = Field(default=None, index=True)   # user messages: the widget's uuid, for safe retries
    created_at: dt.datetime = Field(default_factory=utc_now)


def create_tables(engine=None) -> None:
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine, tables=[ChatThread.__table__, ChatMessage.__table__])
    # Small migration: add columns introduced after the table was first created
    columns = {column["name"] for column in inspect(engine).get_columns(ChatMessage.__tablename__)}
    if "client_message_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {ChatMessage.__tablename__} ADD COLUMN client_message_id VARCHAR"))
            connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_chat_messages_client_message_id "
                                    f"ON {ChatMessage.__tablename__} (client_message_id)"))


# ---------------------------------------------------------------------------
# Small data-access helpers (sync; the API calls them through asyncio.to_thread)
# ---------------------------------------------------------------------------

def create_thread(visitor_id: str, page: str | None) -> ChatThread:
    with Session(get_engine()) as session:
        thread = ChatThread(visitor_id=visitor_id, page=page)
        session.add(thread)
        session.commit()
        session.refresh(thread)
        return thread


def get_visitor_thread(thread_id: str, visitor_id: str) -> ChatThread | None:
    """The thread, only if it belongs to this visitor. Someone else's thread looks like a missing one."""
    with Session(get_engine()) as session:
        thread = session.get(ChatThread, thread_id)
        if thread is None or thread.visitor_id != visitor_id:
            return None
        return thread


def list_messages(thread_id: str) -> list[ChatMessage]:
    with Session(get_engine()) as session:
        return list(session.exec(
            select(ChatMessage).where(ChatMessage.thread_id == thread_id).order_by(ChatMessage.seq)
        ).all())


def list_threads(limit: int = 50, offset: int = 0) -> list[ChatThread]:
    """Newest conversations first for the private admin viewer."""
    with Session(get_engine()) as session:
        return list(session.exec(
            select(ChatThread).order_by(ChatThread.updated_at.desc()).offset(offset).limit(limit)
        ).all())


def get_thread(thread_id: str) -> ChatThread | None:
    with Session(get_engine()) as session:
        return session.get(ChatThread, thread_id)


def find_saved_turn(thread_id: str, client_message_id: str) -> tuple[ChatMessage | None, ChatMessage | None]:
    """(user message, the assistant reply saved right after it) for a client_message_id already seen in
    this thread, else (None, None). Used to answer a retry without running the agent again."""
    with Session(get_engine()) as session:
        user = session.exec(
            select(ChatMessage).where(ChatMessage.thread_id == thread_id,
                                      ChatMessage.client_message_id == client_message_id,
                                      ChatMessage.role == "user")
        ).first()
        if user is None:
            return None, None
        reply = session.exec(
            select(ChatMessage).where(ChatMessage.thread_id == thread_id, ChatMessage.role == "assistant",
                                      ChatMessage.seq > user.seq).order_by(ChatMessage.seq)
        ).first()
        return user, reply


def save_turn(thread_id: str, messages: list[ChatMessage], **thread_updates) -> None:
    """Save this turn's messages and update the thread (last_agent, department, guardrail_flag) together."""
    # expire_on_commit=False: the caller still reads message ids after the commit
    with Session(get_engine(), expire_on_commit=False) as session:
        thread = session.get(ChatThread, thread_id)
        for message in messages:
            message.thread_id = thread_id
            session.add(message)
        for field, value in thread_updates.items():
            if value is not None:
                setattr(thread, field, value)
        thread.updated_at = utc_now()
        session.add(thread)
        session.commit()
