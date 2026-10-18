"""v0.13.2 market-research efficiency: ranked sources, reuse, cache, session cap, fast retry."""
import asyncio
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from app.tools import product_search
from app.tools.adaptation import present_adaptation_options


def _chunk(uri, title):
    return SimpleNamespace(web=SimpleNamespace(uri=uri, title=title))


def _support(*indices):
    return SimpleNamespace(grounding_chunk_indices=list(indices))


def _response(text="Two grip options look relevant.", supports=None, queries=("adaptive spoon grip India",)):
    chunks = [
        _chunk("https://a.example/1", "A"),
        _chunk("https://b.example/2", "B"),
        _chunk("https://c.example/3", "C"),
        _chunk("https://a.example/1", "A duplicate"),
    ]
    metadata = SimpleNamespace(
        grounding_chunks=chunks,
        grounding_supports=supports if supports is not None else [],
        web_search_queries=list(queries),
    )
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(grounding_metadata=metadata)])


ARGS = dict(query="adaptive spoon grip", object_name="Spoon", functional_barrier="thin handle", must_haves=[])


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    product_search.clear_search_cache()
    monkeypatch.setattr(product_search.settings, "product_search_enabled", True)
    monkeypatch.setattr(product_search.settings, "product_search_cache_ttl_seconds", 3600)
    monkeypatch.setattr(product_search.settings, "product_search_cache_max_entries", 16)
    monkeypatch.setattr(product_search.settings, "product_search_max_per_session", 3)
    monkeypatch.setattr(product_search.settings, "product_search_max_sources", 5)
    yield
    product_search.clear_search_cache()


def _count_calls(monkeypatch, response=None):
    calls = []

    def fake(*args, **kwargs):
        calls.append(1)
        return response or _response()

    monkeypatch.setattr(product_search, "_generate_grounded_response", fake)
    return calls


def _run(context, **overrides):
    return asyncio.run(product_search.search_existing_products(tool_context=context, **{**ARGS, **overrides}))


def test_sources_are_ranked_by_citations_and_uncited_chunks_are_dropped():
    response = _response(supports=[_support(2), _support(2, 0), _support(2)])
    sources = product_search._grounding_sources(response, 5)
    assert [s["url"] for s in sources] == ["https://c.example/3", "https://a.example/1"]


def test_sources_without_supports_keep_order_and_respect_limit():
    sources = product_search._grounding_sources(_response(), 2)
    assert [s["url"] for s in sources] == ["https://a.example/1", "https://b.example/2"]


def test_sources_from_the_same_site_are_shown_once():
    chunks = [_chunk("https://redirect/1", "shop.example"), _chunk("https://redirect/2", "Shop.example"), _chunk("https://redirect/3", "other.example")]
    metadata = SimpleNamespace(grounding_chunks=chunks, grounding_supports=[], web_search_queries=[])
    response = SimpleNamespace(text="x", candidates=[SimpleNamespace(grounding_metadata=metadata)])
    sources = product_search._grounding_sources(response, 5)
    assert [s["url"] for s in sources] == ["https://redirect/1", "https://redirect/3"]


def test_search_query_count_is_reported(monkeypatch):
    _count_calls(monkeypatch, _response(queries=("q1", "q2", "q1")))
    result = product_search._search_sync(country="India", **ARGS)
    assert result["search_query_count"] == 2
    assert result["attempt_count"] == 1


def test_same_need_in_same_conversation_is_reused_without_searching(monkeypatch):
    calls = _count_calls(monkeypatch)
    context = SimpleNamespace(state={})
    first = _run(context)
    second = _run(context, query="  Adaptive SPOON grip ", object_name="spoon")
    assert first["status"] == "ready" and first["search_performed"] is True
    assert second["reused"] is True and second["search_performed"] is False
    assert second["sources"] == []
    assert len(calls) == 1
    assert context.state["market_search_count"] == 1
    # The session keeps only a small marker, not a second copy of the research text.
    assert all(set(v) == {"source_count"} for v in context.state["market_search_keys"].values())


def test_identical_need_in_another_conversation_uses_cache(monkeypatch):
    calls = _count_calls(monkeypatch)
    _run(SimpleNamespace(state={}))
    other = SimpleNamespace(state={})
    result = _run(other)
    assert len(calls) == 1
    assert result["cache_hit"] is True and result["market_text"]
    assert other.state["market_check_completed"] is True
    assert other.state.get("market_search_count", 0) == 0  # cache hits do not use the live-search budget


def test_failed_searches_are_not_cached(monkeypatch):
    calls = _count_calls(monkeypatch, _response(text=""))
    _run(SimpleNamespace(state={}))
    _run(SimpleNamespace(state={}))
    assert len(calls) == 2


def test_session_cap_stops_further_live_searches(monkeypatch):
    calls = _count_calls(monkeypatch)
    monkeypatch.setattr(product_search.settings, "product_search_max_per_session", 2)
    monkeypatch.setattr(product_search.settings, "product_search_cache_ttl_seconds", 0)
    context = SimpleNamespace(state={})
    _run(context, query="grip a")
    _run(context, query="grip b")
    capped = _run(context, query="grip c")
    assert len(calls) == 2
    assert capped["status"] == "skipped" and capped["failure_reason"] == "session_search_limit"
    assert context.state["market_check_completed"] is True


def test_fast_transient_failure_is_retried_once(monkeypatch):
    attempts = []

    def flaky(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise genai_errors.ServerError(503, {"error": {"code": 503, "message": "busy", "status": "UNAVAILABLE"}})
        return _response()

    monkeypatch.setattr(product_search, "_generate_grounded_response", flaky)
    monkeypatch.setattr(product_search.time, "sleep", lambda s: None)
    result = product_search._search_sync(country="India", **ARGS)
    assert result["status"] == "ready" and result["attempt_count"] == 2


def test_slow_or_non_transient_failure_is_not_retried(monkeypatch):
    attempts = []

    def failing(*args, **kwargs):
        attempts.append(1)
        raise genai_errors.ClientError(400, {"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}})

    monkeypatch.setattr(product_search, "_generate_grounded_response", failing)
    result = _run(SimpleNamespace(state={}))
    assert len(attempts) == 1
    assert result["status"] == "error" and result["error_code"] == 400



def test_deadline_504_is_retried_but_attempts_are_bounded(monkeypatch):
    attempts = []

    def deadline(*args, **kwargs):
        attempts.append(1)
        raise genai_errors.ServerError(504, {"error": {"code": 504, "message": "late", "status": "DEADLINE_EXCEEDED"}})

    monkeypatch.setattr(product_search, "_generate_grounded_response", deadline)
    monkeypatch.setattr(product_search.time, "sleep", lambda s: None)
    monkeypatch.setattr(product_search.settings, "product_search_max_attempts", 2)
    with pytest.raises(genai_errors.ServerError):
        product_search._generate_with_fast_retry("p", None)
    assert len(attempts) == 2

    attempts.clear()

    def cancelled_then_ok(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise genai_errors.ClientError(499, {"error": {"code": 499, "message": "cancelled", "status": "CANCELLED"}})
        return _response()

    monkeypatch.setattr(product_search, "_generate_grounded_response", cancelled_then_ok)
    assert product_search._generate_with_fast_retry("p", None)[1] == 2

    attempts.clear()
    monkeypatch.setattr(product_search, "_generate_grounded_response", deadline)
    monkeypatch.setattr(product_search.settings, "product_search_max_attempts", 1)
    with pytest.raises(genai_errors.ServerError):
        product_search._generate_with_fast_retry("p", None)
    assert len(attempts) == 1


def test_each_attempt_gets_its_own_short_deadline(monkeypatch):
    from google.genai import types

    monkeypatch.setattr(product_search.settings, "product_search_attempt_timeout_seconds", 25)
    seen = []
    monkeypatch.setattr(product_search, "_generate_grounded_response", lambda p, c, **k: seen.append(c) or _response())
    product_search._generate_with_fast_retry("p", types.GenerateContentConfig(temperature=0.1))
    assert seen[0].http_options.timeout == 25_000
    assert seen[0].temperature == 0.1


def _options(context, strategy="buy_existing", options=None):
    return present_adaptation_options(
        problem_summary="Thin spoon handle.", context_type="object", user_goal="Eat comfortably",
        task="Eating", object_name="Spoon", functional_barrier="Thin handle", decision_rationale="r",
        risk_reason="", options=options if options is not None else [{"strategy": strategy, "title": "t"}],
        recommended_strategy=strategy, requires_measurement=False, professional_review_recommended=False,
        usage_evidence_required=False, tool_context=context,
    )


def test_option_errors_list_allowed_values_so_the_model_can_self_correct():
    context = SimpleNamespace(state={"market_check_completed": True})
    bad = _options(context, strategy="foam_tubing")
    assert bad["error_type"] == "invalid_strategy" and "buy_existing" in bad["error"]
    bad_options = _options(context, options=[{"strategy": "foam_tubing"}, "not-a-dict"])
    assert bad_options["error_type"] == "invalid_options" and "foam_tubing" in bad_options["error"]
    ok = _options(context, strategy="BUY_EXISTING", options=[{"strategy": "Buy_Existing", "title": "t"}])
    assert ok["status"] == "ready" and ok["recommended_strategy"] == "buy_existing"
