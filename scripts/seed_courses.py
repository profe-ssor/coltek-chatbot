"""Create or update (upsert) the Coltek Code Academy courses in the database.

TODO before going live, fill in these values below (None means the bot says "not confirmed yet"):
  web_dev_bootcamp:
    - next_start_date       e.g. dt.date(2027, 1, 18)
    - application_deadline  e.g. dt.date(2027, 1, 8)
    - fee_ghs               e.g. 3500
    - payment_options       e.g. "Full payment or 2 instalments of GHS 1,800"  (any amount here becomes an approved price)
    - seats_left
    - schedule              e.g. "Mon, Wed, Fri 6pm-9pm"
    - certificate           e.g. "Coltek certificate of completion (not an accredited qualification)"
    - status                set to "open" when registration opens
  uxui_masterclass:
    - the same fields as above
Also check name, duration and mode for both courses.

Run from the project root:  python scripts/seed_courses.py
Safe to run again: existing courses are updated, nothing is duplicated. Leads and demo requests are never touched.
"""
import datetime as dt  # noqa: F401  (used when you fill in the dates)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # make `import chatbot` work

from sqlmodel import select  # noqa: E402

from chatbot.db import Course, CourseStatus, get_engine, get_session, utc_now  # noqa: E402

COURSES = [
    {
        "slug": "web_dev_bootcamp",
        "name": "Complete Web Development Bootcamp",
        "status": CourseStatus.not_scheduled,   # TODO: "open" / "waitlist" / "closed" once confirmed
        "next_start_date": None,                # TODO
        "application_deadline": None,           # TODO
        "duration": "12 weeks",                 # TODO: confirm
        "schedule": None,                       # TODO
        "mode": "Hybrid (Accra & Online)",      # TODO: confirm
        "fee_ghs": None,                        # TODO
        "payment_options": None,                # TODO
        "seats_left": None,                     # TODO
        "certificate": None,                    # TODO
    },
    {
        "slug": "uxui_masterclass",
        "name": "UX/UI Design Masterclass",
        "status": CourseStatus.not_scheduled,   # TODO
        "next_start_date": None,                # TODO
        "application_deadline": None,           # TODO
        "duration": "6 weeks",                  # TODO: confirm
        "schedule": None,                       # TODO
        "mode": "Online",                       # TODO: confirm
        "fee_ghs": None,                        # TODO
        "payment_options": None,                # TODO
        "seats_left": None,                     # TODO
        "certificate": None,                    # TODO
    },
]


def upsert_courses(courses: list[dict]) -> None:
    with get_session() as session:
        for data in courses:
            course = session.exec(select(Course).where(Course.slug == data["slug"])).first()
            if course is None:
                course = Course(**data)
                action = "created"
            else:
                for field, value in data.items():
                    setattr(course, field, value)
                action = "updated"
            course.updated_at = utc_now()
            session.add(course)
            print(f"{action:8} {data['slug']:18} status={course.status.value} fee_ghs={course.fee_ghs} "
                  f"start={course.next_start_date}")
        session.commit()


if __name__ == "__main__":
    print("Database:", get_engine().url)
    upsert_courses(COURSES)
