from __future__ import annotations

from google.adk.tools import ToolContext


ALLOWED_CONTEXTS = {"object", "environment"}
ALLOWED_STRATEGIES = {
    "change_technique",
    "buy_existing",
    "modify_object",
    "custom_cad",
    "standard_adaptation",
    "edge_protection",
    "path_clearance",
    "furniture_repositioning",
    "visual_cue",
    "impact_padding",
    "reach_access",
    "custom_environment_fixture",
    "professional_help",
}
# Any strategy that normally introduces a purchasable product/accessory must
# have a live market-search attempt first. Pure no-purchase changes are exempt.
MARKET_REQUIRED_STRATEGIES = {
    "buy_existing",
    "modify_object",
    "custom_cad",
    "standard_adaptation",
    "edge_protection",
    "visual_cue",
    "impact_padding",
    "reach_access",
    "custom_environment_fixture",
}


def _market_check_required(recommended_strategy: str, custom_design_requested: bool) -> bool:
    if recommended_strategy == "custom_cad" and custom_design_requested:
        return False
    return recommended_strategy in MARKET_REQUIRED_STRATEGIES


def _risk_for_recommendation(
    *,
    recommended_strategy: str,
    options: list[dict],
    professional_review_recommended: bool,
) -> str:
    """Deterministically classify recommendation risk for the prototype UI."""
    if recommended_strategy == "professional_help":
        return "RED"
    recommended_option = next(
        (item for item in options if item.get("strategy") == recommended_strategy),
        None,
    )
    if professional_review_recommended or bool((recommended_option or {}).get("requires_professional")):
        return "AMBER"
    return "GREEN"


def _clean_design_features(features: list[dict] | None) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in features or []:
        if not isinstance(item, dict):
            continue
        feature = str(item.get("feature", "")).strip()
        value = str(item.get("value", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not feature or not value:
            continue
        cleaned.append({"feature": feature, "value": value, "reason": reason})
        if len(cleaned) >= 6:
            break
    return cleaned


def present_adaptation_options(
    problem_summary: str,
    context_type: str,
    user_goal: str,
    task: str,
    object_name: str,
    functional_barrier: str,
    decision_rationale: str,
    risk_reason: str,
    options: list[dict],
    recommended_strategy: str,
    requires_measurement: bool,
    professional_review_recommended: bool,
    usage_evidence_required: bool,
    tool_context: ToolContext,
    custom_design_requested: bool = False,
    design_features: list[dict] | None = None,
) -> dict:
    """Compare practical adaptation options and expose concise decision context.

    Allowed values (use exactly these lowercase identifiers):
    - context_type: "object" or "environment".
    - recommended_strategy and each options[].strategy: change_technique, buy_existing,
      modify_object, custom_cad, standard_adaptation, edge_protection, path_clearance,
      furniture_repositioning, visual_cue, impact_padding, reach_access,
      custom_environment_fixture, professional_help.
    - options: list of {"strategy", "title", "rationale", "requires_measurement",
      "requires_professional"}; include the recommended strategy as one of the options.
    - Call search_existing_products first for buy_existing, modify_object, standard_adaptation,
      edge_protection, visual_cue, impact_padding, reach_access, custom_environment_fixture,
      and custom_cad unless custom_design_requested is true.

    The tool intentionally separates the visible "why" behind the recommendation
    from private model reasoning. Risk remains deterministic. Strategies that normally
    use a purchasable product/accessory require a market-search attempt before the
    recommendation can proceed.
    """
    context_type = context_type.strip().lower()
    if context_type not in ALLOWED_CONTEXTS:
        return {
            "status": "error",
            "error": f"context_type must be one of: {', '.join(sorted(ALLOWED_CONTEXTS))}.",
            "error_type": "invalid_context_type",
        }
    recommended_strategy = str(recommended_strategy or "").strip().lower()
    if recommended_strategy not in ALLOWED_STRATEGIES:
        return {
            "status": "error",
            "error": (
                f"Unsupported recommended_strategy '{recommended_strategy}'. "
                f"Use one of: {', '.join(sorted(ALLOWED_STRATEGIES))}."
            ),
            "error_type": "invalid_strategy",
        }

    market_required = _market_check_required(recommended_strategy, custom_design_requested)
    if market_required and not bool(tool_context.state.get("market_check_completed")):
        return {
            "status": "error",
            "error": (
                "A live market check is required before recommending this strategy because it normally "
                "uses a purchasable product/accessory or precedes custom fabrication."
            ),
            "instruction": "Call search_existing_products, then present the adaptation options again.",
            "required_tool": "search_existing_products",
            "error_type": "market_check_required",
        }

    cleaned: list[dict] = []
    rejected: list[str] = []
    for option in options or []:
        if not isinstance(option, dict):
            continue
        strategy = str(option.get("strategy", "")).strip().lower()
        if strategy not in ALLOWED_STRATEGIES:
            rejected.append(strategy or "<missing>")
        title = str(option.get("title", strategy)).strip()
        rationale = str(option.get("rationale", "")).strip()
        if strategy not in ALLOWED_STRATEGIES:
            continue
        cleaned.append({
            "strategy": strategy,
            "title": title,
            "rationale": rationale,
            "requires_measurement": bool(option.get("requires_measurement", False)),
            "requires_professional": bool(option.get("requires_professional", False)),
        })

    if not cleaned:
        return {
            "status": "error",
            "error": (
                "At least one supported adaptation option is required. "
                + (f"Unsupported option strategies: {', '.join(rejected)}. " if rejected else "")
                + f"Each options[].strategy must be one of: {', '.join(sorted(ALLOWED_STRATEGIES))}."
            ),
            "error_type": "invalid_options",
        }

    risk_level = _risk_for_recommendation(
        recommended_strategy=recommended_strategy,
        options=cleaned,
        professional_review_recommended=professional_review_recommended,
    )
    if risk_level == "GREEN":
        professional_review_recommended = False
    elif risk_level in {"AMBER", "RED"}:
        professional_review_recommended = True

    feature_summary = _clean_design_features(design_features)
    result = {
        "status": "ready",
        "problem_summary": problem_summary.strip(),
        "context_type": context_type,
        "user_goal": user_goal.strip(),
        "task": task.strip(),
        "object_name": object_name.strip(),
        "functional_barrier": functional_barrier.strip(),
        "decision_rationale": decision_rationale.strip(),
        "design_features": feature_summary,
        "options": cleaned,
        "recommended_strategy": recommended_strategy,
        "requires_measurement": bool(requires_measurement),
        "professional_review_recommended": bool(professional_review_recommended),
        "usage_evidence_required": bool(usage_evidence_required),
        "custom_design_requested": bool(custom_design_requested),
        "market_check_skipped": bool(custom_design_requested and recommended_strategy == "custom_cad"),
        "market_research_required": market_required,
        "market_check_completed": bool(tool_context.state.get("market_check_completed")),
        "market_check_status": tool_context.state.get("market_check_status"),
        "risk_level": risk_level,
        "risk_reason": risk_reason.strip() or (
            "Low-risk everyday adaptation within the prototype scope."
            if risk_level == "GREEN"
            else "Professional review is appropriate before implementation."
        ),
    }
    tool_context.state["adaptation_options"] = result
    tool_context.state["risk_level"] = risk_level
    tool_context.state["professional_review_recommended"] = bool(professional_review_recommended)
    tool_context.state["usage_evidence_required"] = bool(usage_evidence_required)
    tool_context.state["custom_design_requested"] = bool(custom_design_requested)
    return result
