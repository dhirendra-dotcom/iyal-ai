from google.adk.agents import Agent
from google.adk.tools.load_memory_tool import LoadMemoryTool
from google.genai import types

from app.config import settings
from app.prompts import ARTHISTICS_INSTRUCTION
from app.resilient_model import ResilientGemini
from app.tools.cad import generate_3d_design
from app.tools.measurement import register_manual_measurement
from app.tools.measurement_async import measure_object_from_capture
from app.tools.measurement_plan import present_measurement_plan
from app.tools.product_search import search_existing_products
from app.tools.validation import validate_design
from app.tools.video import register_usage_video
from app.tools.preview import generate_usage_preview, generate_environment_preview
from app.tools.adaptation import present_adaptation_options
from app.tools.support_assessment import assess_support_need
from app.tools.support import offer_product_support
from app.memory_context import generate_memories_callback, remember_adaptation_preference
from app.turns import count_user_turn
from app.observability import (
    before_model_callback,
    after_model_callback,
    on_model_error_callback,
    before_tool_callback,
    after_tool_callback,
    on_tool_error_callback,
)


# v0.10.0 intentionally has no BuiltInPlanner. Gemini Flash performs normal
# conversational routing/tool selection; deterministic workflow guards live in Python.
agent_tools = [
    present_measurement_plan,
    register_usage_video,
    measure_object_from_capture,
    register_manual_measurement,
    present_adaptation_options,
    search_existing_products,
    validate_design,
    generate_3d_design,
    generate_usage_preview,
    generate_environment_preview,
    assess_support_need,
    offer_product_support,
]

if settings.managed_memory_enabled:
    # Retrieval is model-directed rather than injected into every prompt.
    agent_tools.extend([LoadMemoryTool(), remember_adaptation_preference])


root_agent = Agent(
    name="arthistics_agent",
    description=(
        "Iyal.ai: low-risk everyday adaptation assistant that checks current market options, "
        "measures fit when needed, validates the supported grip-sleeve CAD family, and supports "
        "optional human fit review."
    ),
    # v0.13.2: bounded wait for the first chunk; see app/resilient_model.py.
    model=ResilientGemini(model=settings.gemini_model),
    instruction=ARTHISTICS_INSTRUCTION,
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=2048,
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.LOW,
            include_thoughts=False,
        ),
    ),
    before_agent_callback=count_user_turn,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
    on_model_error_callback=on_model_error_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    on_tool_error_callback=on_tool_error_callback,
    after_agent_callback=generate_memories_callback,
    tools=agent_tools,
)
