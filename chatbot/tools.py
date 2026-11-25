"""@function_tool functions backed by the database (chatbot/db.py).

Tool names, model-visible parameters and docstrings are unchanged from Part 3.
Each tool's first parameter `ctx` is the run context: the Agents SDK hides it from the model,
so visitor_id and source_page always come from the server, never from the model.
"""
from typing import Any, Literal, Optional

from agents import RunContextWrapper, function_tool
from sqlmodel import func, select

from chatbot.context import context_values
from chatbot.db import Course, DemoRequest, Lead, get_session, utc_now
from chatbot.notify import notify_team


def normalise_ghana_phone(phone: str) -> str:
    """Clean a phone number and convert Ghana numbers to E.164: 054 123 4567 -> +233541234567."""
    phone = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if phone.startswith("0") and len(phone) == 10:
        phone = "+233" + phone[1:]
    elif phone.startswith("233") and len(phone) == 12:
        phone = "+" + phone
    return phone


def _iso(value):
    """Dates and datetimes as ISO strings, so the tool result is plain JSON."""
    return value.isoformat() if value is not None else None


@function_tool
def check_course_intake(
    ctx: RunContextWrapper[Any],
    slug: Literal["web_dev_bootcamp", "uxui_masterclass"]
) -> dict:
    """
    Look up live schedule, fee, mode, status, and seat availability for a Coltek Code Academy course.
    Call this tool whenever a visitor asks about dates, fees, duration, mode, or availability for a specific course.
    If any field in the returned dictionary is None, treat that specific detail as not yet confirmed and never guess or invent a value for it.
    """
    with get_session() as session:
        course = session.exec(select(Course).where(Course.slug == slug)).first()

    if not course:
        return {
            "error": "COURSE_NOT_FOUND",
            "message": f"No course found for slug '{slug}'."
        }

    return {
        "slug": course.slug,
        "name": course.name,
        "status": course.status.value,
        "next_start_date": _iso(course.next_start_date),
        "application_deadline": _iso(course.application_deadline),
        "duration": course.duration,
        "schedule": course.schedule,
        "mode": course.mode,
        "fee_ghs": course.fee_ghs,
        "payment_options": course.payment_options,
        "seats_left": course.seats_left,
        "certificate": course.certificate,
        "updated_at": _iso(course.updated_at),
    }


@function_tool
def save_lead(
    ctx: RunContextWrapper[Any],
    full_name: str,
    phone: str,
    interest: Literal["services", "academy", "opendoor", "other"],
    need_summary: str,
    preferred_contact_method: str,
    consent: bool,
    email: Optional[str] = None,
) -> dict:
    # 1. Stop if they didn't give consent
    if not consent:
        return {"error": "CONSENT_REQUIRED", "message": "Visitor must give consent first."}

    # 2. Clean spaces and convert 054... to +23354...
    phone = normalise_ghana_phone(phone)
    visitor_id, source_page = context_values(ctx)

    with get_session() as session:
        # 3. Check if this phone number is already saved for the same interest
        existing = session.exec(
            select(Lead).where(Lead.phone == phone, Lead.interest == interest)
        ).first()
        if existing:
            return {
                "error": "DUPLICATE_LEAD",
                "message": f"Already saved under {existing.reference}."
            }

        # 4. Save, then create the reference from the row ID (CT-L-000001, CT-L-000002, ...)
        lead = Lead(
            full_name=full_name.strip(),
            phone=phone,
            email=email,
            interest=interest,
            need_summary=need_summary.strip(),
            preferred_contact=preferred_contact_method.strip(),
            consent=consent,
            consent_at=utc_now(),
            visitor_id=visitor_id,
            source_page=source_page,
        )
        session.add(lead)
        session.flush()                       # assigns lead.id
        lead.reference = f"CT-L-{lead.id:06d}"
        session.commit()
        ref = lead.reference

    # 5. Tell the team (never fails the tool; logs a warning if email is not set up)
    notify_team(
        f"New {interest} lead {ref}: {full_name}",
        f"Reference: {ref}\nName: {full_name}\nPhone: {phone}\nEmail: {email or '-'}\n"
        f"Interest: {interest}\nPreferred contact: {preferred_contact_method}\nNeed: {need_summary}\n"
        f"Source page: {source_page or '-'}\nVisitor ID: {visitor_id or '-'}\n",
    )

    # 6. Return the reference and next step
    return {
        "reference": ref,
        "message": f"Saved! Your reference is {ref}. The Coltek team will contact you soon."
    }


@function_tool
def request_opendoor_demo(
    ctx: RunContextWrapper[Any],
    church_name: str,
    contact_name: str,
    role: str,
    phone: str,
    approximate_members: int,
    city: str,
    main_need: str,
    email: Optional[str] = None,
) -> dict:
    """
    Book an OpenDoor church management software demo for a church.
    Call this tool when a visitor wants to schedule a demo or evaluation of OpenDoor and has provided their church details and contact info.
    """
    # 1. Clean spaces and convert 054... to +23354...
    phone = normalise_ghana_phone(phone)
    visitor_id, _source_page = context_values(ctx)

    with get_session() as session:
        # 2. Check if this church and phone number already requested a demo
        existing = session.exec(
            select(DemoRequest).where(
                DemoRequest.phone == phone,
                func.lower(DemoRequest.church_name) == church_name.strip().lower(),
            )
        ).first()
        if existing:
            return {
                "error": "DUPLICATE_DEMO_REQUEST",
                "message": f"A demo for {church_name} is already logged under {existing.reference}."
            }

        # 3. Save, then create the reference from the row ID (CT-D-000001, ...)
        #    The agent only calls this tool after the visitor clearly agreed to be contacted
        #    (OpenDoor instructions), so consent is recorded as given at this moment.
        demo = DemoRequest(
            church_name=church_name.strip(),
            contact_name=contact_name.strip(),
            role=role.strip(),
            phone=phone,
            email=email,
            approx_members=approximate_members,
            city_region=city.strip(),
            main_need=main_need.strip(),
            consent=True,
            consent_at=utc_now(),
            visitor_id=visitor_id,
        )
        session.add(demo)
        session.flush()
        demo.reference = f"CT-D-{demo.id:06d}"
        session.commit()
        ref = demo.reference

    # 4. Tell the OpenDoor team
    notify_team(
        f"New OpenDoor demo request {ref}: {church_name.strip()}",
        f"Reference: {ref}\nChurch: {church_name}\nContact: {contact_name} ({role})\nPhone: {phone}\n"
        f"Email: {email or '-'}\nApprox. members: {approximate_members}\nCity/region: {city}\n"
        f"Main need: {main_need}\nVisitor ID: {visitor_id or '-'}\n",
    )

    # 5. Return the reference and next step
    return {
        "reference": ref,
        "message": f"Demo request saved! Your reference is {ref}. The OpenDoor team will reach out shortly to schedule your session."
    }
