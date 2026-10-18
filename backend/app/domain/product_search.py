from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from typing import Any


def extract_json_payload(text: str) -> dict[str, Any] | None:
    """Best-effort parser for model JSON, tolerating markdown fences/preamble."""
    if not text.strip():
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(cleaned[start : end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _safe_http_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    return text if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def normalize_products(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    products = payload.get("products")
    if not isinstance(products, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in products:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "") or "").strip()
        if not name:
            continue
        normalized.append(
            {
                "name": name,
                "product_type": str(raw.get("product_type", "") or "").strip(),
                "brand": str(raw.get("brand", "") or "").strip(),
                "seller": str(raw.get("seller", "") or "").strip(),
                "source_url": _safe_http_url(raw.get("source_url")),
                "price_text": str(raw.get("price_text", "") or "").strip(),
                "availability_note": str(raw.get("availability_note", "") or "").strip(),
                "fit_summary": str(raw.get("fit_summary", "") or "").strip(),
                "limitations": str(raw.get("limitations", "") or "").strip(),
            }
        )
        if len(normalized) >= limit:
            break
    return normalized
