from types import SimpleNamespace

from app.config import settings
from app.domain.identity import is_valid_custom_session_id, new_session_id, new_user_id
from app.domain.product_search import normalize_products
from app.domain.memory_policy import normalize_memory_candidate, outcome_memory_fact


def test_agent_platform_identity_formats():
    session_id = new_session_id()
    user_id = new_user_id()
    assert is_valid_custom_session_id(session_id)
    assert len(session_id) <= 63
    assert user_id.startswith("usr-")
    assert len(user_id) <= 128


def test_market_products_keep_only_safe_source_urls():
    payload = {
        "products": [
            {
                "name": "Bendable Spoon A",
                "product_type": "bendable spoon",
                "source_url": "https://example.com/product/a",
            },
            {
                "name": "Unsafe URL",
                "source_url": "javascript:alert(1)",
            },
        ]
    }
    products = normalize_products(payload, 5)
    assert products[0]["source_url"] == "https://example.com/product/a"
    assert products[0]["product_type"] == "bendable spoon"
    assert products[1]["source_url"] == ""


def test_memory_policy_accepts_preference_and_rejects_health_details():
    result = normalize_memory_candidate(
        "design_preference",
        "User found a 32 mm grip too thick and preferred an oval contour.",
    )
    assert result["status"] == "ready"
    assert result["category"] == "design_preference"

    rejected = normalize_memory_candidate(
        "fit_feedback",
        "User has wrist pain and arthritis.",
    )
    assert rejected["status"] == "rejected"


def test_memory_feature_flag_requires_both_switch_and_id(monkeypatch):
    monkeypatch.setattr(settings, "memory_enabled", False)
    monkeypatch.setattr(settings, "vertex_memory_bank_id", "123")
    assert settings.managed_memory_enabled is False
    monkeypatch.setattr(settings, "memory_enabled", True)
    assert settings.managed_memory_enabled is True


def test_outcome_memory_fact_is_non_medical_and_keeps_useful_design_preference():
    fact = outcome_memory_fact(
        "much_easier",
        design_state={"current_design": {"profile": "oval", "texture": "ribbed"}},
    )
    assert "oval profile" in fact
    assert "ribbed texture" in fact
    assert "much easier" in fact
    assert "pain" not in fact.lower()


def test_market_retry_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "product_search_retry_unparseable", False)
    assert settings.product_search_retry_unparseable is False
