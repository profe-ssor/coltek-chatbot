"""The agent's conversation memory: Agents SDK SQLAlchemySession, one session per chat thread.

Verified against openai-agents 0.25.0:
  SQLAlchemySession(session_id, *, engine: AsyncEngine, create_tables, sessions_table, messages_table,
                    session_settings)  with get_items(limit) / add_items(items) / pop_item()
It needs an *async* engine, so DATABASE_URL is converted automatically:
  sqlite:///./chatbot.sqlite3   -> sqlite+aiosqlite:////<project>/chatbot.sqlite3
  postgresql://...              -> postgresql+asyncpg://...   (pip install asyncpg)

The session stores every item the model sees: visitor messages, replies, tool calls WITH their
arguments (e.g. the name and phone passed to save_lead), tool results and handoffs.
It is personal data: include agent_sessions/agent_messages in backups, deletion requests and
retention clean-up. Never log session items.

IMPORTANT (verified offline): when a guardrail trips, the SDK has already saved the blocked
input (and, for output trips, possibly more items of that turn). chat_service rewinds the session
to the item count it had before the run (rewind_to), so blocked text never stays in memory.
"""
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from agents.extensions.memory import SQLAlchemySession
from agents.memory import SessionSettings

from chatbot.config import PROJECT_ROOT, settings

SESSIONS_TABLE = "agent_sessions"
MESSAGES_TABLE = "agent_messages"

_engine: AsyncEngine | None = None


def to_async_url(url: str) -> str:
    """Turn our sync DATABASE_URL into the async-driver URL the SDK session needs."""
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend == "sqlite":
        database = parsed.database
        if database and database != ":memory:" and not database.startswith("/"):
            database = str((PROJECT_ROOT / database).resolve())   # same file as chatbot/db.py uses
        parsed = parsed.set(drivername="sqlite+aiosqlite", database=database)
    elif backend == "postgresql":
        parsed = parsed.set(drivername="postgresql+asyncpg")
    return parsed.render_as_string(hide_password=False)


def get_async_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(to_async_url(settings.database_url))
    return _engine


def use_async_engine(engine: AsyncEngine | None) -> None:
    """Swap the engine (tests point it at their temporary database; None = rebuild from settings)."""
    global _engine
    _engine = engine


def get_agent_session(thread_id: str) -> SQLAlchemySession:
    return SQLAlchemySession(
        thread_id,
        engine=get_async_engine(),
        create_tables=True,
        sessions_table=SESSIONS_TABLE,
        messages_table=MESSAGES_TABLE,
        session_settings=SessionSettings(limit=settings.session_history_limit),  # what the model sees
    )


async def count_items(session: SQLAlchemySession) -> int:
    """All items stored for this session (not limited by session_history_limit)."""
    await session.get_items(limit=0)          # makes sure the SDK's tables exist
    async with get_async_engine().connect() as connection:
        result = await connection.execute(
            text(f"SELECT COUNT(*) FROM {MESSAGES_TABLE} WHERE session_id = :session_id"),
            {"session_id": session.session_id},
        )
        return int(result.scalar_one())


async def rewind_to(session: SQLAlchemySession, item_count: int) -> int:
    """Remove every item added after the session had `item_count` items. Returns how many were removed."""
    removed = 0
    while await count_items(session) > item_count:
        await session.pop_item()
        removed += 1
    return removed
