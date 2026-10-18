"""Calibrated measurement: Gemini localizes on a downscaled copy with bounded attempts."""
import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from google.genai import errors as genai_errors

from app.domain import segmentation


SEGMENT = {
    "label": "spoon handle",
    "box_2d": [100, 200, 900, 300],
    "mask": [[0, 0], [1000, 0], [1000, 1000]],
    "fully_visible": True,
    "capture_quality": "good",
    "issues": [],
}


def _jpeg(width, height):
    ok, encoded = cv2.imencode(".jpg", np.full((height, width, 3), 255, np.uint8))
    assert ok
    return encoded.tobytes()


class _Models:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


@pytest.fixture
def models(monkeypatch):
    def install(*outcomes):
        fake = _Models(outcomes)
        monkeypatch.setattr(segmentation, "_client", lambda force_new=False: SimpleNamespace(models=fake))
        return fake
    return install


def test_large_photo_is_downscaled_for_gemini_only():
    small, mime = segmentation._downscale_for_localization(_jpeg(4000, 3000), "image/jpeg")
    image = cv2.imdecode(np.frombuffer(small, np.uint8), cv2.IMREAD_COLOR)
    assert mime == "image/jpeg"
    assert max(image.shape[:2]) == segmentation.settings.segmentation_max_image_px


def test_small_photo_keeps_its_size():
    small, _ = segmentation._downscale_for_localization(_jpeg(800, 600), "image/jpeg")
    image = cv2.imdecode(np.frombuffer(small, np.uint8), cv2.IMREAD_COLOR)
    assert image.shape[:2] == (600, 800)


def test_undecodable_bytes_pass_through_unchanged():
    assert segmentation._downscale_for_localization(b"not an image", "image/png") == (b"not an image", "image/png")


def test_fast_path_returns_segmentation(models):
    fake = models(json.dumps(SEGMENT))
    result = segmentation.segment_target_region_bytes(_jpeg(3000, 2000), "image/jpeg", "handle", "spoon")
    assert result.box_2d == SEGMENT["box_2d"]
    assert len(fake.calls) == 1


def test_stalled_attempt_is_retried(models):
    fake = models(genai_errors.ServerError(504, {"error": {"code": 504, "message": "late", "status": "DEADLINE_EXCEEDED"}}), json.dumps(SEGMENT))
    result = segmentation.segment_target_region_bytes(_jpeg(1000, 800), "image/jpeg", "handle", "spoon")
    assert result.fully_visible is True
    assert len(fake.calls) == 2


def test_non_transient_failure_falls_back_to_interactions(models, monkeypatch):
    models(genai_errors.ClientError(400, {"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}}))
    monkeypatch.setattr(segmentation, "_create_interaction", lambda **kwargs: SimpleNamespace(output_text=json.dumps(SEGMENT)))
    result = segmentation.segment_target_region_bytes(_jpeg(1000, 800), "image/jpeg", "handle", "spoon")
    assert result.label == "spoon handle"
