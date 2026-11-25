"""The old fake course data from Parts 3-5, used only by tests.

Tests load it into a temporary SQLite database (see conftest.py). It is NOT real Coltek data.
"""
import datetime as dt

from chatbot.db import Course, CourseStatus

# The original dictionary from the notebooks, unchanged
FAKE_COURSES = {
    "web_dev_bootcamp": {
        "status": "Open for registration",
        "next_start_date": "2027-01-18",
        "duration": "12 weeks",
        "mode": "Hybrid (Accra & Online)",
        "fee": "GHS 3,500",
        "seats_left": 6,
    },
    "uxui_masterclass": {
        "status": "Upcoming",
        "next_start_date": None,  # Set to None to test the "not confirmed" path
        "duration": "6 weeks",
        "mode": "Online",
        "fee": None,              # Set to None to test the "not confirmed" path
        "seats_left": None,
    },
}

FAKE_COURSE_NAMES = {
    "web_dev_bootcamp": "Complete Web Development Bootcamp",
    "uxui_masterclass": "UX/UI Design Masterclass",
}

STATUS_MAP = {"Open for registration": CourseStatus.open, "Upcoming": CourseStatus.not_scheduled}


def fake_course_rows() -> list[Course]:
    """FAKE_COURSES converted to Course rows for the test database."""
    rows = []
    for slug, data in FAKE_COURSES.items():
        fee = data["fee"]
        start = data["next_start_date"]
        rows.append(Course(
            slug=slug,
            name=FAKE_COURSE_NAMES[slug],
            status=STATUS_MAP[data["status"]],
            next_start_date=dt.date.fromisoformat(start) if start else None,
            duration=data["duration"],
            mode=data["mode"],
            fee_ghs=float(fee.replace("GHS", "").replace(",", "").strip()) if fee else None,
            seats_left=data["seats_left"],
        ))
    return rows
