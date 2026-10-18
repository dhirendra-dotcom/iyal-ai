import pytest

from app.outcomes import record_outcome


def test_record_outcome_accepts_supported_value():
    result = record_outcome(
        session_id="ses_test",
        user_id="usr_test",
        outcome="much_easier",
        comment="Grip felt more comfortable.",
        design_version=2,
    )
    assert result["outcome"] == "much_easier"
    assert result["design_version"] == 2
    assert result["outcome_id"].startswith("OUT-")


def test_record_outcome_rejects_unknown_value():
    with pytest.raises(ValueError):
        record_outcome(
            session_id="ses_test",
            user_id="usr_test",
            outcome="perfect",
        )
