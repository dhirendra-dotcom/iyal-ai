from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from app.tools import measurement, measurement_async


def _result(dimensions):
    return {
        "status": "ok",
        "photo_dimensions": dimensions,
        "manual_required_dimensions": [],
        "reference_type": "a4",
        "quality_score": 0.9,
        "target_minor_mm": 12.0,
        "target_major_mm": 100.0,
    }


def test_measurement_keeps_event_loop_responsive_and_preserves_manual_values(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def compute(*args):
        started.set()
        assert release.wait(3), "Event loop did not release measurement worker"
        return _result(args[3])

    monkeypatch.setattr(measurement_async, "_compute_capture_measurement", compute)
    context = SimpleNamespace(state={})

    async def run():
        task = asyncio.create_task(measurement_async.measure_object_from_capture(
            "gs://bucket/photo", "spoon", "handle", ["interface_width_mm"], "a4", context
        ))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            measurement.register_manual_measurement("interface_depth_mm", 4, context)
            measurement.register_manual_measurement("interface_width_mm", 15, context)
        finally:
            release.set()
        return await task

    result = asyncio.run(run())
    assert result["interface_width_mm"] == 15
    assert result["ready_for_cad_fit"] is True
    geometry = context.state["object_geometry"]
    assert geometry["interface_depth_mm"] == 4
    assert geometry["measurements"]["interface_width_mm"]["source"] == "user_measurement"


def test_parallel_captures_merge_into_current_geometry(monkeypatch):
    workers = threading.Barrier(2, timeout=3)

    def compute(*args):
        workers.wait()
        return _result(args[3])

    monkeypatch.setattr(measurement_async, "_compute_capture_measurement", compute)
    context = SimpleNamespace(state={})

    async def run():
        return await asyncio.gather(*(
            measurement_async.measure_object_from_capture(
                f"gs://bucket/{dimension}", "spoon", "handle", [dimension], "a4", context
            )
            for dimension in ["interface_width_mm", "available_length_mm"]
        ))

    results = asyncio.run(run())
    assert all(result["status"] == "ok" for result in results)
    geometry = context.state["object_geometry"]
    assert geometry["interface_width_mm"] == 12
    assert geometry["available_length_mm"] == 100
    assert len(geometry["captures"]) == 2
    assert set(geometry["measurements"]) == {"interface_width_mm", "available_length_mm"}


def test_failed_measurement_does_not_mutate_state(monkeypatch):
    monkeypatch.setattr(measurement_async, "_compute_capture_measurement", lambda *args: {
        "status": "recapture_required", "reason": "Keep the target visible."
    })
    context = SimpleNamespace(state={"object_geometry": {"interface_depth_mm": 4}})
    result = asyncio.run(measurement_async.measure_object_from_capture(
        "gs://bucket/photo", "spoon", "handle", ["interface_width_mm"], "a4", context
    ))
    assert result["status"] == "recapture_required"
    assert context.state == {"object_geometry": {"interface_depth_mm": 4}}


def test_synchronous_measurement_api_still_computes_and_records(monkeypatch):
    monkeypatch.setattr(measurement, "_download_gcs", lambda uri: (b"photo", "image/jpeg"))
    monkeypatch.setattr(measurement, "segment_target_region_bytes", lambda **kwargs: SimpleNamespace(
        fully_visible=True, capture_quality="good", box_2d=[0, 0, 1000, 1000],
        mask=[], model_dump=lambda: {"capture_quality": "good"},
    ))
    monkeypatch.setattr(measurement, "_measure_segmented_target_bytes", lambda **kwargs: {
        "status": "ok", "target_minor_mm": 12, "target_major_mm": 100,
        "quality_score": 0.9, "reference_type": "a4",
    })
    context = SimpleNamespace(state={})
    result = measurement.measure_object_from_capture(
        "gs://bucket/photo", "spoon", "handle", ["interface_width_mm"], "a4", context
    )
    assert result["status"] == "ok"
    assert context.state["object_geometry"]["interface_width_mm"] == 12
    assert result["measurements"]["interface_width_mm"]["source"] == "calibrated_photo"
