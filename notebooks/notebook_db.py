"""Notebook helper: run the notebooks on a SEPARATE test database, never the real chatbot.sqlite3.

Use it in the first cell that imports anything from chatbot/:

    from notebooks.notebook_db import use_test_database, all_leads, all_demo_requests, all_courses, clear_leads_and_demos
    use_test_database()          # must run BEFORE `from chatbot... import ...`
    from chatbot.tools import ...

The test database is notebooks/notebooks_test.sqlite3 (ignored by git). It is filled with the same
fake courses the tests use (tests/fixtures.py): bootcamp GHS 3,500 starting 18 Jan 2027, masterclass unconfirmed.
"""
import os
import sys

TEST_DATABASE_URL = "sqlite:///notebooks/notebooks_test.sqlite3"   # relative paths are resolved from the project root


def use_test_database() -> str:
    """Point chatbot/ at the notebook test database and add the fake courses. Returns the database URL."""
    if "chatbot.config" in sys.modules and os.environ.get("DATABASE_URL") != TEST_DATABASE_URL:
        raise RuntimeError("chatbot/ was already imported with the real database. "
                           "Restart the kernel and run use_test_database() before importing chatbot.")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL   # beats DATABASE_URL in .env (also after load_dotenv)

    from sqlmodel import Session, select
    from chatbot.db import Course, get_engine
    from tests.fixtures import fake_course_rows

    engine = get_engine()
    url = str(engine.url)
    assert "notebooks_test" in url, f"not the notebook test database: {url}"
    with Session(engine) as session:
        for row in fake_course_rows():
            if session.exec(select(Course).where(Course.slug == row.slug)).first() is None:
                session.add(row)
        session.commit()
    print("Using the notebook test database:", url)
    return url


def all_courses():
    from sqlmodel import Session, select
    from chatbot.db import Course, get_engine
    with Session(get_engine()) as session:
        return list(session.exec(select(Course)).all())


def all_leads():
    from sqlmodel import Session, select
    from chatbot.db import Lead, get_engine
    with Session(get_engine()) as session:
        return list(session.exec(select(Lead).order_by(Lead.id)).all())


def all_demo_requests():
    from sqlmodel import Session, select
    from chatbot.db import DemoRequest, get_engine
    with Session(get_engine()) as session:
        return list(session.exec(select(DemoRequest).order_by(DemoRequest.id)).all())


def clear_leads_and_demos() -> None:
    """Delete all leads and demo requests from the notebook test database (never the real one)."""
    from sqlmodel import Session
    from chatbot.db import DemoRequest, Lead, get_engine
    assert "notebooks_test" in str(get_engine().url)
    with Session(get_engine()) as session:
        for row in all_leads() + all_demo_requests():
            session.delete(session.merge(row))
        session.commit()
