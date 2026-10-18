from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_market_search_returns_grounded_text_not_product_json():
    source = (ROOT / "backend/app/tools/product_search.py").read_text(encoding="utf-8")
    assert "market_text" in source
    assert "response.text" not in source  # access is intentionally via getattr for SDK tolerance
    assert "extract_json_payload" not in source
    assert "normalize_products" not in source
    assert "Return ONLY a JSON object" not in source
    assert "Do not return JSON" in source


def test_market_research_is_rendered_in_conversation_and_workspace_is_status_only():
    source = (ROOT / "frontend-lite/app.js").read_text(encoding="utf-8")
    assert "showMarketResearch" in source
    assert "MARKET RESEARCH · GOOGLE SEARCH GROUNDED" in source
    assert "showMarketStatus('progress')" in source
    assert "showMarketStatus(result.status==='ready'?'completed':'failed',result)" in source
    assert "No concrete product option was verified strongly enough" not in source
    assert "Try this option" not in source


def test_agent_is_told_not_to_repeat_displayed_market_research():
    prompt = (ROOT / "backend/app/prompts.py").read_text(encoding="utf-8")
    assert "Do not repeat the full market-research answer" in prompt
