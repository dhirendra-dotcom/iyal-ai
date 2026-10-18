from __future__ import annotations

import asyncio
import hashlib
import re
import threading
import time
from collections import Counter, OrderedDict
from typing import Any

from google import genai
from google.adk.tools import ToolContext
from google.genai import errors as genai_errors
from google.genai import types

from app.config import settings


_client_instance: genai.Client | None = None
_client_lock = threading.Lock()

# Per-instance cache of successful grounded answers, keyed by the normalized need.
# Identical needs (same object, barrier, intent, constraints, country) within the TTL
# reuse the earlier answer instead of paying for and waiting on another grounded search.
_cache: "OrderedDict[str, tuple[float, dict[str, Any]]]" = OrderedDict()
_cache_lock = threading.Lock()

# 499 = CANCELLED: Vertex returns it when the forwarded per-attempt deadline expires.
TRANSIENT_STATUS_CODES = {429, 499, 500, 502, 503, 504}


def _client(force_new: bool = False) -> genai.Client:
    global _client_instance
    with _client_lock:
        if force_new or _client_instance is None:
            _client_instance = genai.Client(
                http_options=types.HttpOptions(
                    timeout=settings.product_search_timeout_seconds * 1000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                )
            )
        return _client_instance


def _field(value: Any, name: str, default: Any = None) -> Any:
    """Read an SDK object or dict field without depending on one SDK shape."""
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def search_cache_key(
    *, query: str, object_name: str, functional_barrier: str, must_haves: list[str], country: str
) -> str:
    """Stable identity of one market-research need."""
    parts = [
        _normalize(query),
        _normalize(object_name),
        _normalize(functional_barrier),
        "|".join(sorted(_normalize(m) for m in must_haves or [] if str(m).strip())),
        _normalize(country),
    ]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


def _cache_get(key: str) -> dict[str, Any] | None:
    ttl = settings.product_search_cache_ttl_seconds
    if ttl <= 0 or settings.product_search_cache_max_entries <= 0:
        return None
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            return None
        stored_at, result = item
        if time.monotonic() - stored_at > ttl:
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return dict(result)


def _cache_put(key: str, result: dict[str, Any]) -> None:
    limit = settings.product_search_cache_max_entries
    if settings.product_search_cache_ttl_seconds <= 0 or limit <= 0:
        return
    with _cache_lock:
        _cache[key] = (time.monotonic(), dict(result))
        _cache.move_to_end(key)
        while len(_cache) > limit:
            _cache.popitem(last=False)


def clear_search_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _grounding_sources(response: Any, limit: int) -> list[dict[str, str]]:
    """Extract deduplicated Google Search grounding links from a GenAI response.

    When grounding supports are present, only chunks that actually back part of the
    answer are kept, most-cited first. Without supports, chunk order is preserved.
    """
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    # Grounding URIs are opaque redirects whose title is the site's domain, so two pages
    # from one site look identical to the user. Keep one link per title for variety.
    seen_titles: set[str] = set()
    for candidate in _field(response, "candidates", []) or []:
        metadata = _field(candidate, "grounding_metadata")
        chunks = list(_field(metadata, "grounding_chunks", []) or [])
        citations: Counter[int] = Counter()
        for support in _field(metadata, "grounding_supports", []) or []:
            for index in _field(support, "grounding_chunk_indices", []) or []:
                if isinstance(index, int) and 0 <= index < len(chunks):
                    citations[index] += 1
        if citations:
            order = sorted(citations, key=lambda i: (-citations[i], i))
        else:
            order = list(range(len(chunks)))
        for index in order:
            web = _field(chunks[index], "web")
            uri = str(_field(web, "uri", "") or "").strip()
            title = str(_field(web, "title", "") or "").strip()
            if not uri or uri in seen or (title and title.lower() in seen_titles):
                continue
            seen.add(uri)
            if title:
                seen_titles.add(title.lower())
            sources.append({"title": title or uri, "url": uri})
            if len(sources) >= limit:
                return sources
    return sources


def _search_query_count(response: Any) -> int:
    """Number of Google Search queries Gemini actually executed (billing/latency signal)."""
    queries: set[str] = set()
    for candidate in _field(response, "candidates", []) or []:
        metadata = _field(candidate, "grounding_metadata")
        for query in _field(metadata, "web_search_queries", []) or []:
            if str(query).strip():
                queries.add(str(query).strip())
    return len(queries)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return getattr(exc, "code", None) in TRANSIENT_STATUS_CODES
    # Client-side deadline (httpx.TimeoutException and friends) without importing httpx here.
    return "timeout" in type(exc).__name__.lower()


def _generate_grounded_response(prompt: str, config: types.GenerateContentConfig, *, force_new: bool = False):
    try:
        return _client(force_new=force_new).models.generate_content(
            model=settings.product_search_model,
            contents=prompt,
            config=config,
        )
    except RuntimeError as exc:
        if "closed" not in str(exc).lower():
            raise
        return _client(force_new=True).models.generate_content(
            model=settings.product_search_model,
            contents=prompt,
            config=config,
        )


def _attempt_config(config: Any) -> Any:
    """Give each attempt its own deadline (the SDK also forwards it as the server deadline)."""
    if not isinstance(config, types.GenerateContentConfig):
        return config
    return config.model_copy(
        update={"http_options": types.HttpOptions(timeout=settings.product_search_attempt_timeout_seconds * 1000)}
    )


def _generate_with_fast_retry(prompt: str, config: types.GenerateContentConfig) -> tuple[Any, int]:
    """Bounded attempts: retry only transient failures (429, 5xx including 504, timeouts)."""
    attempts = max(1, settings.product_search_max_attempts)
    attempt_config = _attempt_config(config)
    for attempt in range(1, attempts + 1):
        try:
            return _generate_grounded_response(prompt, attempt_config), attempt
        except Exception as exc:
            if attempt >= attempts or not _is_transient(exc):
                raise
            time.sleep(1.0)
    raise RuntimeError("unreachable")


def _search_sync(
    *,
    query: str,
    object_name: str,
    functional_barrier: str,
    must_haves: list[str],
    country: str,
) -> dict[str, Any]:
    """Run Google Search grounding and return the grounded conversational answer directly.

    Market research is intentionally not converted into application-defined product JSON.
    The model's grounded response text is shown to the user, while grounding metadata is
    returned separately so the UI can render source links below the research answer.
    """
    if not settings.product_search_enabled:
        return {
            "status": "not_configured",
            "configured": False,
            "search_performed": False,
            "query": query,
            "country": country,
            "market_text": "Public-web product search is disabled.",
            "sources": [],
            "source_count": 0,
            "failure_reason": "product_search_disabled",
            "disclaimer": "No live market search was performed.",
        }

    must_have_text = "\n".join(f"- {item}" for item in must_haves if item.strip()) or "- none specified"
    prompt = f"""
You are performing a current market check for a low-risk everyday adaptation.
Use Google Search to research commercially available solutions relevant to the user's exact need.
Prefer options that appear purchasable in or deliverable to {country} when current evidence supports that.

Search efficiently: start with one focused query that combines the object, the barrier and {country}.
Run at most one more query, and only if the first results do not contain a concrete relevant option.

User need:
- object/task object: {object_name}
- functional barrier: {functional_barrier}
- search intent: {query}
- must-have constraints:
{must_have_text}

Write a concise, user-facing market-research response suitable for displaying directly in a conversation.
Keep it under 220 words. When reliable current evidence is available, cover the 2-3 most relevant existing
options or solution approaches. For each, use one short paragraph or bullet that explains:
- what the option is,
- why it may or may not fit this user's need,
- the most important fit or compatibility unknown,
- price or availability only when clearly supported by current search evidence.
End with one sentence naming the option that looks most promising for this need, or say that none is clearly suitable.

Rules:
- Do not invent product names, sellers, prices, stock, delivery, certifications, clinical claims, or benefits.
- A product existing on the market does not automatically mean it fits this user; state fit uncertainties clearly.
- Use plain everyday language. Avoid clinical or diagnostic terms; describe how the hand or task is affected instead.
- If current search evidence is insufficient to verify a concrete product, say that plainly instead of inventing one.
- Do not return JSON, a schema, code fences, markdown links, or application-internal fields.
- Do not add a separate Sources/Search sources section; the application will render Google grounding links below your answer.
- Do not recommend unsafe structural, load-bearing, clinical, or regulated-device solutions as a substitute for professional assessment.
""".strip()

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1,
        max_output_tokens=1536,
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.LOW,
            include_thoughts=False,
        ),
    )

    started = time.monotonic()
    response, attempts = _generate_with_fast_retry(prompt, config)
    market_text = str(getattr(response, "text", "") or "").strip()
    sources = _grounding_sources(response, settings.product_search_max_sources)
    timing = {
        "attempt_count": attempts,
        "search_query_count": _search_query_count(response),
        "search_duration_ms": round((time.monotonic() - started) * 1000),
    }

    if not market_text:
        return {
            "status": "error",
            "configured": True,
            "search_performed": True,
            "query": query,
            "country": country,
            "market_text": "The live market search completed, but no research summary was returned.",
            "sources": sources,
            "source_count": len(sources),
            "failure_reason": "empty_grounded_response",
            "disclaimer": "Continue without claiming that the market was exhaustively searched.",
            **timing,
        }

    return {
        "status": "ready",
        "configured": True,
        "search_performed": True,
        "query": query,
        "country": country,
        "market_text": market_text,
        "sources": sources,
        "source_count": len(sources),
        "failure_reason": None,
        "disclaimer": (
            "Live web market check. Product fit is not guaranteed; price, stock and delivery can change. "
            "Verify the seller listing before purchase."
        ),
        **timing,
    }


def _record(tool_context: ToolContext, result: dict[str, Any], *, key: str, live: bool) -> dict[str, Any]:
    history = dict(tool_context.state.get("market_search_keys") or {})
    if result.get("status") == "ready":
        # Keep session state small: the full text already lives in the conversation history.
        history[key] = {"source_count": int(result.get("source_count") or 0)}
    tool_context.state["market_search_keys"] = history
    if live:
        tool_context.state["market_search_count"] = int(tool_context.state.get("market_search_count") or 0) + 1
    tool_context.state["product_search"] = result
    tool_context.state["market_check_completed"] = True
    tool_context.state["market_check_skipped"] = False
    tool_context.state["market_check_status"] = result.get("status")
    return result


async def search_existing_products(
    query: str,
    object_name: str,
    functional_barrier: str,
    must_haves: list[str],
    tool_context: ToolContext,
    country: str = "",
    skip_context_question: bool = False,
) -> dict[str, Any]:
    """Search the current public web once for a distinct need before recommending a purchasable adaptation.

    The tool returns grounded conversational market-research text plus Google Search
    grounding links. It does not attempt to transform the answer into product-card JSON.
    Call it once per distinct need; repeating the same need in a conversation reuses the
    earlier research instead of searching again.

    On the user's first message the tool asks you to put the context question first.
    Set skip_context_question=true only when the user explicitly asked for existing or
    ready-made products, or already said which object they use and when the problem happens.
    """
    state = tool_context.state
    if (
        not skip_context_question
        and int(state.get("user_turn_count") or 0) == 1
        and not state.get("market_search_keys")
    ):
        # Enforced here because the prompt rule alone was skipped in live runs.
        return {
            "status": "context_question_first",
            "search_performed": False,
            "instruction": (
                "Do not search yet. Reply with one short context question and stop: which spoon or utensil "
                "they use most (for example a soup spoon or a smaller dessert spoon), whether it twists more "
                "in particular moments such as lifting liquids, and whether their fingers close fully around "
                "the handle. Search after they answer."
            ),
        }
    resolved_country = country.strip() or settings.product_search_country
    key = search_cache_key(
        query=query,
        object_name=object_name,
        functional_barrier=functional_barrier,
        must_haves=must_haves,
        country=resolved_country,
    )

    # 1. Same need already researched in this conversation: do not search or re-display.
    earlier = (tool_context.state.get("market_search_keys") or {}).get(key)
    if earlier:
        tool_context.state["market_check_completed"] = True
        tool_context.state["market_check_status"] = "ready"
        return {
            "status": "ready",
            "configured": True,
            "search_performed": False,
            "reused": True,
            "query": query,
            "country": resolved_country,
            "market_text": (
                "Market research for this same need was already shown earlier in this conversation. "
                "Use that research; do not repeat it."
            ),
            "sources": [],
            "source_count": int(earlier.get("source_count") or 0),
            "failure_reason": None,
        }

    # 2. Per-conversation cap on live grounded searches.
    if int(tool_context.state.get("market_search_count") or 0) >= settings.product_search_max_per_session:
        tool_context.state["market_check_completed"] = True
        return {
            "status": "skipped",
            "configured": True,
            "search_performed": False,
            "reused": True,
            "query": query,
            "country": resolved_country,
            "market_text": (
                "The market-research limit for this conversation has been reached. Use the research already "
                "shown above. If it does not cover this need, say so and continue with generic low-risk guidance."
            ),
            "sources": [],
            "source_count": 0,
            "failure_reason": "session_search_limit",
        }

    # 3. Same need researched recently in another conversation on this instance.
    cached = _cache_get(key)
    if cached is not None:
        cached.update(cache_hit=True, search_performed=False, search_duration_ms=0)
        return _record(tool_context, cached, key=key, live=False)

    # 4. Live grounded search.
    try:
        result = await asyncio.to_thread(
            _search_sync,
            query=query.strip(),
            object_name=object_name.strip(),
            functional_barrier=functional_barrier.strip(),
            must_haves=must_haves,
            country=resolved_country,
        )
    except Exception as exc:
        result = {
            "status": "error",
            "configured": True,
            "search_performed": True,
            "query": query,
            "country": resolved_country,
            "market_text": "The live market check could not be completed.",
            "sources": [],
            "source_count": 0,
            "failure_reason": type(exc).__name__,
            "error_code": getattr(exc, "code", None),
            "error": str(exc)[:500],
            "disclaimer": "Continue without claiming that the market was exhaustively searched.",
        }

    if result.get("status") == "ready":
        _cache_put(key, result)
    return _record(tool_context, result, key=key, live=bool(result.get("search_performed")))
