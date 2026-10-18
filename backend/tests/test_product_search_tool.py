from types import SimpleNamespace

from app.tools import product_search


def _grounded_response(text: str):
    return SimpleNamespace(
        text=text,
        candidates=[
            SimpleNamespace(
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=[
                        SimpleNamespace(web=SimpleNamespace(uri="https://example.com/grip", title="Grip listing")),
                        SimpleNamespace(web=SimpleNamespace(uri="https://example.com/grip", title="Duplicate")),
                    ]
                )
            )
        ],
    )


def test_grounding_sources_are_extracted_and_deduplicated():
    result = product_search._grounding_sources(_grounded_response("research"), 5)
    assert result == [{"title": "Grip listing", "url": "https://example.com/grip"}]


def test_grounded_market_text_is_returned_without_json_parsing(monkeypatch):
    text = (
        "I found two current grip approaches: foam build-up tubing and an adaptive utensil handle. "
        "The main fit uncertainty is the spoon-handle width."
    )
    calls = []

    def fake_generate(*args, **kwargs):
        calls.append(bool(kwargs.get("force_new")))
        return _grounded_response(text)

    monkeypatch.setattr(product_search, "_generate_grounded_response", fake_generate)
    monkeypatch.setattr(product_search.settings, "product_search_enabled", True)

    result = product_search._search_sync(
        query="adaptive spoon grip",
        object_name="spoon",
        functional_barrier="small handle",
        must_haves=[],
        country="India",
    )

    assert result["status"] == "ready"
    assert result["market_text"] == text
    assert result["search_performed"] is True
    assert result["source_count"] == 1
    assert "products" not in result
    assert "market_summary" not in result
    assert calls == [False]


def test_empty_grounded_text_returns_real_failure_not_parse_failure(monkeypatch):
    monkeypatch.setattr(product_search, "_generate_grounded_response", lambda *args, **kwargs: _grounded_response(""))
    monkeypatch.setattr(product_search.settings, "product_search_enabled", True)

    result = product_search._search_sync(
        query="adaptive spoon grip",
        object_name="spoon",
        functional_barrier="small handle",
        must_haves=[],
        country="India",
    )

    assert result["status"] == "error"
    assert result["failure_reason"] == "empty_grounded_response"
    assert result["source_count"] == 1
