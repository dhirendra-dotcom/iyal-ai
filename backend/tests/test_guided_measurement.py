from __future__ import annotations

import cv2
import numpy as np

from app.domain.measurement_core import (
    _detect_a4_reference,
    _measure_segmented_target_bytes,
)


def _synthetic_a4_with_handle() -> tuple[bytes, list[int], list[list[int]]]:
    # Dark table background, white A4 sheet in landscape orientation.
    canvas = np.full((900, 1400, 3), 55, dtype=np.uint8)
    # A4 aspect ratio: 297 / 210 ~= 1.414. 990 x 700 keeps that ratio.
    x0, y0, x1, y1 = 200, 100, 1190, 800
    cv2.rectangle(canvas, (x0, y0), (x1, y1), (245, 245, 245), -1)

    # Target handle on the A4 plane: 400 px long x 30 px thick.
    hx0, hy0, hx1, hy1 = 430, 430, 830, 460
    cv2.rectangle(canvas, (hx0, hy0), (hx1, hy1), (20, 20, 20), -1)

    h, w = canvas.shape[:2]
    # Whole-image normalized bbox [ymin, xmin, ymax, xmax].
    box = [
        round(hy0 / h * 1000),
        round(hx0 / w * 1000),
        round(hy1 / h * 1000),
        round(hx1 / w * 1000),
    ]
    # Rectangle polygon normalized inside bbox.
    mask = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]

    ok, encoded = cv2.imencode(".png", canvas)
    assert ok
    return encoded.tobytes(), box, mask


def test_a4_reference_detection():
    data, _, _ = _synthetic_a4_with_handle()
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    ref = _detect_a4_reference(image)
    assert ref is not None
    assert ref.kind == "a4"
    assert {round(ref.width_mm), round(ref.height_mm)} == {210, 297}
    assert ref.quality > 0.7


def test_segmented_target_measured_from_a4():
    data, box, mask = _synthetic_a4_with_handle()
    result = _measure_segmented_target_bytes(data, box, mask, "a4")
    assert result["status"] == "ok", result
    assert result["reference_type"] == "a4"
    # 990px maps to 297mm => 3.333 px/mm. 400px ~= 120mm; 30px ~= 9mm.
    assert 112 <= result["target_major_mm"] <= 126, result
    assert 7 <= result["target_minor_mm"] <= 11, result
    assert result["quality_score"] > 0.6


def test_a4_missing_requests_recapture():
    canvas = np.full((500, 700, 3), 70, dtype=np.uint8)
    cv2.rectangle(canvas, (100, 220), (600, 250), (240, 240, 240), -1)
    ok, encoded = cv2.imencode(".png", canvas)
    assert ok
    result = _measure_segmented_target_bytes(
        encoded.tobytes(),
        [400, 150, 550, 850],
        [[0, 0], [1000, 0], [1000, 1000], [0, 1000]],
        "a4",
    )
    assert result["status"] == "recapture_required"
    assert "a4" in result["reason"].lower()
