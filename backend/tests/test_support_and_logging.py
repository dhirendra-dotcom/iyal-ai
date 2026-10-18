from __future__ import annotations

import io
import json
import logging
from datetime import date

from app import support_booking
from app.logging_config import JsonFormatter, log_event


def test_support_booking_reserves_slot_and_simulates_email(monkeypatch):
    support_booking._BOOKINGS.clear()
    monkeypatch.setattr(support_booking.settings, "smtp_host", "")
    monkeypatch.setattr(support_booking.settings, "support_email_from", "")

    first = support_booking.get_available_slots(days=1)[0]
    slot = first["times"][0]
    booking = support_booking.create_booking(
        session_id="ses_test",
        user_id="usr_test",
        visit_date=first["date"],
        time_slot=slot,
        visit_type="in_person",
        email="person@example.com",
    )

    assert booking["email_status"] == "simulated"
    assert booking["booking_id"].startswith("ART-")
    refreshed = support_booking.get_available_slots(days=1)[0]
    if refreshed["date"] == first["date"]:
        assert slot not in refreshed["times"]


def test_support_booking_keeps_reservation_if_email_fails(monkeypatch):
    support_booking._BOOKINGS.clear()
    first = support_booking.get_available_slots(days=1)[0]
    slot = first["times"][0]

    def fail_email(*args, **kwargs):
        raise OSError("smtp unavailable")

    monkeypatch.setattr(support_booking, "_send_email", fail_email)
    booking = support_booking.create_booking(
        session_id="ses_email",
        user_id="usr_email",
        visit_date=first["date"],
        time_slot=slot,
        visit_type="video_review",
        email="person@example.com",
    )

    assert booking["email_status"] == "failed"
    assert booking["booking_id"] in support_booking._BOOKINGS


def test_json_formatter_exposes_structured_fields():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("arthistics.test.structured")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    log_event(
        logger,
        logging.INFO,
        "Tool completed",
        event_type="tool_complete",
        session_id="ses_123",
        turn_id="turn_456",
        tool_name="measure_object_from_capture",
        duration_ms=123,
        status="success",
    )

    payload = json.loads(stream.getvalue())
    assert payload["event_type"] == "tool_complete"
    assert payload["session_id"] == "ses_123"
    assert payload["turn_id"] == "turn_456"
    assert payload["tool_name"] == "measure_object_from_capture"
    assert payload["duration_ms"] == 123
    assert payload["status"] == "success"


def test_invalid_booking_email_is_rejected():
    support_booking._BOOKINGS.clear()
    first = support_booking.get_available_slots(days=1)[0]
    try:
        support_booking.create_booking(
            session_id="ses_bad",
            user_id="usr_bad",
            visit_date=first["date"],
            time_slot=first["times"][0],
            visit_type="in_person",
            email="not-an-email",
        )
    except ValueError as exc:
        assert "valid email" in str(exc).lower()
    else:
        raise AssertionError("invalid email should be rejected")
