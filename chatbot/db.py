"""Database tables and connection (SQLModel). Reads DATABASE_URL from .env via chatbot/config.py.

Tables: courses, leads, demo_requests.
Tests never use the real database: tests/conftest.py points DATABASE_URL at a temporary file
and calls use_engine() with a fresh SQLite database for every test.
"""
import datetime as dt
import enum

from sqlalchemy.engine import make_url
from sqlmodel import Field, Session, SQLModel, create_engine

from chatbot.config import PROJECT_ROOT, settings


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class CourseStatus(str, enum.Enum):
    open = "open"
    waitlist = "waitlist"
    closed = "closed"
    not_scheduled = "not_scheduled"


class Course(SQLModel, table=True):
    __tablename__ = "courses"

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    name: str
    status: CourseStatus = CourseStatus.not_scheduled
    # Every detail below is nullable: None means "not confirmed yet" and the bot must say so.
    next_start_date: dt.date | None = None
    application_deadline: dt.date | None = None
    duration: str | None = None
    schedule: str | None = None
    mode: str | None = None
    fee_ghs: float | None = None
    payment_options: str | None = None
    seats_left: int | None = None
    certificate: str | None = None
    updated_at: dt.datetime = Field(default_factory=utc_now)


class Lead(SQLModel, table=True):
    __tablename__ = "leads"

    id: int | None = Field(default=None, primary_key=True)
    reference: str | None = Field(default=None, unique=True, index=True)   # CT-L-000001, set after insert
    full_name: str
    phone: str = Field(index=True)          # E.164, e.g. +233241234567
    email: str | None = None
    interest: str                           # services / academy / opendoor / other
    organisation: str | None = None
    need_summary: str
    preferred_contact: str
    consent: bool
    consent_at: dt.datetime | None = None
    visitor_id: str | None = Field(default=None, index=True)   # from the run context, never from the model
    source_page: str | None = None                             # from the run context, never from the model
    status: str = "new"
    created_at: dt.datetime = Field(default_factory=utc_now)


class DemoRequest(SQLModel, table=True):
    __tablename__ = "demo_requests"

    id: int | None = Field(default=None, primary_key=True)
    reference: str | None = Field(default=None, unique=True, index=True)   # CT-D-000001, set after insert
    church_name: str
    contact_name: str
    role: str
    phone: str = Field(index=True)          # E.164
    email: str | None = None
    approx_members: int
    city_region: str
    main_need: str
    consent: bool
    consent_at: dt.datetime | None = None
    visitor_id: str | None = Field(default=None, index=True)
    status: str = "new"
    created_at: dt.datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _resolve_sqlite_path(url: str) -> str:
    """Make a relative SQLite path relative to the project root, not to the current folder.

    Without this, sqlite:///./chatbot.sqlite3 would create a different database file
    when code runs from notebooks/ or scripts/.
    """
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite") and parsed.database and parsed.database != ":memory:":
        path = (PROJECT_ROOT / parsed.database).resolve() if not parsed.database.startswith("/") else parsed.database
        return parsed.set(database=str(path)).render_as_string(hide_password=False)
    return url


def make_engine(url: str):
    url = _resolve_sqlite_path(url)
    parsed = make_url(url)
    if parsed.get_backend_name() == "postgresql":
        # Neon supplies postgresql:// URLs. Use psycopg 3 explicitly instead of
        # SQLAlchemy's legacy psycopg2 default; the same dialect works async too.
        url = parsed.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}   # tools run in worker threads
    return create_engine(url, connect_args=connect_args)


_engine = None


def get_engine():
    """The shared engine, created on first use from DATABASE_URL. Tables are created if missing."""
    global _engine
    if _engine is None:
        _engine = make_engine(settings.database_url)
        SQLModel.metadata.create_all(_engine)
    return _engine


def use_engine(engine) -> None:
    """Swap the engine (used by tests to point at a temporary database)."""
    global _engine
    _engine = engine
    SQLModel.metadata.create_all(_engine)


def get_session() -> Session:
    return Session(get_engine())
