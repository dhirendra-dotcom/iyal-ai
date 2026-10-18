from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any

from app.config import settings
from app.logging_config import get_logger, log_event


logger = get_logger("arthistics.booking")
_BOOKINGS: dict[str, dict[str, Any]] = {}


TIME_SLOTS = ["10:00 AM", "12:30 PM", "3:00 PM", "5:30 PM"]


def get_available_slots(days: int = 7) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    # One appointment capacity per displayed time slot in the hackathon demo.
    # A production scheduler would query real staff/resource availability.
    booked = {(b["date"], b["time_slot"]) for b in _BOOKINGS.values()}
    cursor = date.today() + timedelta(days=1)
    while len(results) < days:
        if cursor.weekday() < 6:  # Monday-Saturday
            date_value = cursor.isoformat()
            available_times = [slot for slot in TIME_SLOTS if (date_value, slot) not in booked]
            if available_times:
                results.append({"date": date_value, "label": cursor.strftime("%a, %d %b"), "times": available_times})
        cursor += timedelta(days=1)
    return results


def _send_email(to_email: str, booking: dict[str, Any]) -> str:
    if not to_email:
        raise ValueError("Email is required for booking confirmation.")
    if not settings.smtp_host or not settings.support_email_from:
        return "simulated"

    msg = EmailMessage()
    msg["Subject"] = f"Iyal.ai product-support visit {booking['booking_id']}"
    msg["From"] = settings.support_email_from
    msg["To"] = to_email
    msg.set_content(
        "Your Iyal.ai product-support visit is confirmed.\n\n"
        f"Date: {booking['date']}\n"
        f"Time: {booking['time_slot']}\n"
        f"Visit type: {booking['visit_type']}\n"
        f"Booking ID: {booking['booking_id']}\n\n"
        "This visit is for product/design support and is not a medical consultation."
    )

    context = ssl.create_default_context()
    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=context)
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(msg)
    return "sent"


def bookings_for_session(session_id: str) -> list[dict[str, Any]]:
    """Confirmed visits for one conversation (per instance; the prototype runs one instance)."""
    return sorted(
        (b for b in _BOOKINGS.values() if b["session_id"] == session_id),
        key=lambda b: b["created_at"],
    )


def booking_context(session_id: str) -> str:
    """Visits are booked outside the agent run, so tell Gemini what has been confirmed."""
    bookings = bookings_for_session(session_id)
    if not bookings:
        return ""
    lines = [
        f"- {b['visit_type'].replace('_', ' ')} on {b['date']} at {b['time_slot']} (booking ID {b['booking_id']})"
        for b in bookings
    ]
    return (
        "\n\nApplication context (not typed by the user): confirmed fit-review visits in this conversation:\n"
        + "\n".join(lines)
        + "\nDo not offer to book another visit unless the user asks."
    )


def create_booking(*, session_id: str, user_id: str, visit_date: str, time_slot: str, visit_type: str, email: str) -> dict[str, Any]:
    valid_dates = {entry["date"]: entry for entry in get_available_slots()}
    if visit_date not in valid_dates:
        raise ValueError("Selected visit date is no longer available.")
    if time_slot not in valid_dates[visit_date]["times"]:
        raise ValueError("Selected time slot is no longer available.")
    if visit_type not in {"video_review", "in_person"}:
        raise ValueError("Unsupported visit type.")
    if not email or "@" not in email:
        raise ValueError("Enter a valid email address for the confirmation.")
    if any(
        b["date"] == visit_date and b["time_slot"] == time_slot
        for b in _BOOKINGS.values()
    ):
        raise ValueError("That slot was just booked. Please choose another time.")

    booking = {
        "booking_id": f"ART-{uuid.uuid4().hex[:8].upper()}",
        "session_id": session_id,
        "user_id": user_id,
        "date": visit_date,
        "time_slot": time_slot,
        "visit_type": visit_type,
        "email": email,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Reserve the booking even if the optional SMTP delivery later fails.
    # This prevents an email outage from losing an already confirmed slot.
    _BOOKINGS[booking["booking_id"]] = booking
    try:
        email_status = _send_email(email, booking)
        booking["email_error"] = None
    except Exception as exc:
        email_status = "failed"
        booking["email_error"] = str(exc)[:1000]
        log_event(
            logger,
            logging.ERROR,
            "Booking confirmation email failed",
            event_type="support_booking_email_error",
            session_id=session_id,
            status="error",
            error_type=type(exc).__name__,
            booking_id=booking["booking_id"],
        )
    booking["email_status"] = email_status

    log_event(
        logger,
        logging.INFO if email_status in {"sent", "simulated"} else logging.WARNING,
        "Product-support visit booked",
        event_type="support_booking",
        session_id=session_id,
        status="confirmed",
        booking_id=booking["booking_id"],
        visit_date=visit_date,
        time_slot=time_slot,
        visit_type=visit_type,
        email_status=email_status,
    )
    return booking

