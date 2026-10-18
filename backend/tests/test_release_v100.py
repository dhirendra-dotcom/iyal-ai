from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_root_prompt_is_compact_and_agent_search_free():
    prompt_source = (ROOT / "backend/app/prompts.py").read_text(encoding="utf-8")
    assert len(prompt_source) < 10_000
    assert "search_design_knowledge" not in prompt_source
    assert "research_adaptation_options" not in prompt_source


def test_root_agent_has_no_builtin_planner_or_design_search():
    source = (ROOT / "backend/app/agent.py").read_text(encoding="utf-8")
    assert "from google.adk.planners import BuiltInPlanner" not in source
    assert "planner=" not in source
    assert "search_design_knowledge" not in source
    assert "research_adaptation_options" not in source
    assert "ThinkingLevel.LOW" in source


def test_deploy_script_has_no_agent_search_or_planner_env():
    source = (ROOT / "scripts/deploy-lite.sh").read_text(encoding="utf-8")
    assert "AGENT_SEARCH_" not in source
    assert "GEMINI_THINKING_LEVEL" not in source
    assert "VERTEX_SESSION_RUNTIME_ID" in source
    assert "VERTEX_MEMORY_BANK_ID" in source


def test_removed_design_search_files_are_absent():
    assert not (ROOT / "backend/app/tools/search_knowledge.py").exists()
    assert not (ROOT / "backend/app/tools/research.py").exists()
