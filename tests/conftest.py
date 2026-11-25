"""Test setup: a temporary database for every test, email and tracing switched off, no real data touched.

The environment variables below are set BEFORE anything from chatbot/ is imported, so the
real DATABASE_URL and SMTP settings in .env are never used (environment variables beat .env).
"""
import os
import sys
import tempfile
from pathlib import Path

_SESSION_DB = Path(tempfile.mkdtemp(prefix="coltek-tests-")) / "session.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite:///{_SESSION_DB}"
os.environ["SMTP_HOST"] = ""
os.environ["NOTIFY_EMAIL_TO"] = ""
# No traces are uploaded to OpenAI from tests (the SDK otherwise exports them even when a run
# never calls a model, using whatever key is in the environment).
os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # make `import chatbot` work

import pytest  # noqa: E402
from agents import set_tracing_disabled  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from sqlmodel import Session  # noqa: E402

from chatbot import db  # noqa: E402
from chatbot.config import settings  # noqa: E402

set_tracing_disabled(True)
assert settings.database_url == os.environ["DATABASE_URL"], "tests must never use the real database"


@pytest.fixture(autouse=True)
def test_db(tmp_path):
    """A fresh SQLite database for each test, filled with the fake courses from tests/fixtures.py.

    The agent-memory sessions (server/sessions.py) use the same temporary file through an async
    engine. NullPool: no connection outlives the event loop of the test that opened it.
    """
    from server import sessions
    from tests.fixtures import fake_course_rows

    db_file = tmp_path / "test.sqlite3"
    engine = db.make_engine(f"sqlite:///{db_file}")
    db.use_engine(engine)
    sessions.use_async_engine(create_async_engine(f"sqlite+aiosqlite:///{db_file}", poolclass=NullPool))
    with Session(engine) as session:
        for row in fake_course_rows():
            session.add(row)
        session.commit()
    yield engine
    sessions.use_async_engine(None)
    engine.dispose()
