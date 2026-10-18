from __future__ import annotations

import cv2
import numpy as np

from app.config import settings
from app.domain.measurement_core import _aruco_dictionary, _measure_bytes


def _synthetic_calibrated_spoon() -> bytes:
    canvas = np.full((900, 1400, 3), 255, dtype=np.uint8)

    # 300 px marker for a configured 100 mm marker -> 3 px/mm.
    marker = cv2.aruco.generateImageMarker(
        _aruco_dictionary(), settings.calibration_marker_id, 300
    )
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    canvas[70:370, 70:370] = marker_bgr

    # A simple spoon-like silhouette on the same plane.
    # Handle: 24 px = 8 mm; total object length roughly 600 px = 200 mm.
    cv2.rectangle(canvas, (500, 438), (1070, 462), (25, 25, 25), -1)
    cv2.ellipse(canvas, (1120, 450), (70, 52), 0, 0, 360, (25, 25, 25), -1)

    ok, encoded = cv2.imencode(".png", canvas)
    assert ok
    return encoded.tobytes()


def test_top_measurement_uses_marker_scale():
    result = _measure_bytes(_synthetic_calibrated_spoon(), "top")
    assert result["status"] == "ok", result
    assert result["measurement_source"] == "calibrated_capture"
    assert 6.0 <= result["interface_width_mm"] <= 10.5, result
    assert result["object_length_mm"] > 150
    assert result["quality_score"] > 0.5


def test_missing_marker_requests_recapture():
    canvas = np.full((500, 700, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (100, 240), (600, 260), (0, 0, 0), -1)
    ok, encoded = cv2.imencode(".png", canvas)
    assert ok
    result = _measure_bytes(encoded.tobytes(), "top")
    assert result["status"] == "recapture_required"
    assert "marker" in result["reason"].lower()
