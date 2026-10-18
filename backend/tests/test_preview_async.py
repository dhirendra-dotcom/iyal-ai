import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.tools import preview


@pytest.mark.parametrize("environment", [False, True])
def test_preview_keeps_loop_responsive_and_saves_on_loop(monkeypatch, environment):
    loop_thread = threading.get_ident()
    release = threading.Event()
    started = threading.Event()
    saved = []

    def render(**kwargs):
        assert threading.get_ident() != loop_thread
        assert kwargs["tool_context"] is not context
        started.set()
        assert release.wait(3), "Event loop blocked during image generation"
        return {"status": "generated_bytes", "image_bytes": b"image", "mime_type": "image/png", "artifact_key": "preview.png"}

    async def save(key, part):
        assert threading.get_ident() == loop_thread
        saved.append(key)
        return 2

    context = SimpleNamespace(
        state={"current_design": {"outer_width_mm": 28}, "current_design_version": 1},
        session=SimpleNamespace(id="ses_test"), save_artifact=save,
    )
    monkeypatch.setattr(preview, "_generate_environment_preview_bytes" if environment else "_generate_usage_preview_bytes", render)

    async def run():
        task = asyncio.create_task(
            preview.generate_environment_preview("gs://room", ["Clear path"], context)
            if environment else preview.generate_usage_preview("spoon", "eating", "", context)
        )
        try:
            async with asyncio.timeout(2):
                while not started.is_set():
                    await asyncio.sleep(0.01)
            release.set()
            return await task
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    result = asyncio.run(run())
    assert result["status"] == "success"
    assert result["artifact_version"] == 2
    assert "image_bytes" not in result
    assert saved == ["preview.png"]


def test_preview_failure_does_not_save_artifact(monkeypatch):
    monkeypatch.setattr(preview, "_generate_usage_preview_bytes", lambda **kwargs: {"status": "error", "error": "unavailable"})
    context = SimpleNamespace(state={})
    result = asyncio.run(preview.generate_usage_preview("spoon", "eating", "", context))
    assert result["status"] == "error"
