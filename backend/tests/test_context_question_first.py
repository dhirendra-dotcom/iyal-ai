"""The first message of a new need gets a context question before any market search."""
import asyncio
from types import SimpleNamespace

from app.turns import count_user_turn
from app.tools import product_search


ARGS = dict(query="adaptive spoon grip", object_name="Spoon", functional_barrier="spoon rotates", must_haves=[])


def _search(state, **overrides):
    context = SimpleNamespace(state=state)
    return asyncio.run(product_search.search_existing_products(tool_context=context, **{**ARGS, **overrides}))


def test_first_turn_asks_the_context_question_without_searching(monkeypatch):
    monkeypatch.setattr(product_search, "_search_sync", lambda **kwargs: (_ for _ in ()).throw(AssertionError("searched")))
    result = _search({"user_turn_count": 1})
    assert result["status"] == "context_question_first"
    assert "soup spoon" in result["instruction"]


def test_explicit_product_request_can_skip_the_question(monkeypatch):
    monkeypatch.setattr(product_search, "_search_sync", lambda **kwargs: {"status": "ready", "market_text": "x", "sources": [], "source_count": 0})
    monkeypatch.setattr(product_search.settings, "product_search_enabled", True)
    product_search.clear_search_cache()
    result = _search({"user_turn_count": 1}, skip_context_question=True)
    assert result["status"] != "context_question_first"


def test_second_turn_searches_normally(monkeypatch):
    monkeypatch.setattr(product_search, "_search_sync", lambda **kwargs: {"status": "ready", "market_text": "x", "sources": [], "source_count": 0})
    monkeypatch.setattr(product_search.settings, "product_search_enabled", True)
    product_search.clear_search_cache()
    assert _search({"user_turn_count": 2})["status"] != "context_question_first"


def test_user_turns_are_counted():
    context = SimpleNamespace(state={})
    count_user_turn(context)
    count_user_turn(context)
    assert context.state["user_turn_count"] == 2
