from __future__ import annotations

import base64
import math
from dataclasses import dataclass
import cv2
import numpy as np
from app.config import settings


@dataclass(frozen=True)
class MarkerDetection:
    corners: np.ndarray  # shape (4, 2), source-image pixels
    marker_id: int
    marker_quality: float


def _aruco_dictionary():
    name = settings.calibration_marker_dictionary.strip().upper()
    if not hasattr(cv2.aruco, name):
        raise RuntimeError(f"Unsupported ArUco dictionary: {name}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


def _decode_image(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The uploaded file could not be decoded as an image.")
    return image


def _detect_reference_marker(image: np.ndarray) -> MarkerDetection | None:
    dictionary = _aruco_dictionary()
    params = cv2.aruco.DetectorParameters()

    if hasattr(cv2.aruco, "ArucoDetector"):
        detector = cv2.aruco.ArucoDetector(dictionary, params)
        corners, ids, _ = detector.detectMarkers(image)
    else:
        corners, ids, _ = cv2.aruco.detectMarkers(image, dictionary, parameters=params)

    if ids is None or not len(ids):
        return None

    ids_flat = ids.flatten().tolist()
    try:
        index = ids_flat.index(settings.calibration_marker_id)
    except ValueError:
        return None

    pts = np.asarray(corners[index], dtype=np.float32).reshape(4, 2)
    side_lengths = [
        float(np.linalg.norm(pts[(i + 1) % 4] - pts[i])) for i in range(4)
    ]
    mean_side = max(float(np.mean(side_lengths)), 1e-6)
    cv = float(np.std(side_lengths) / mean_side)
    # A perspective view naturally gives some edge variation. This is a simple
    # quality score for UI/flow control, not a statistical measurement certainty.
    quality = max(0.0, min(1.0, 1.0 - cv * 2.5))
    return MarkerDetection(corners=pts, marker_id=settings.calibration_marker_id, marker_quality=quality)


def _expanded_marker_polygon(corners: np.ndarray, margin_px: float = 18.0) -> np.ndarray:
    center = np.mean(corners, axis=0)
    vectors = corners - center
    lengths = np.linalg.norm(vectors, axis=1)
    scale = 1.0 + margin_px / max(float(np.mean(lengths)), 1.0)
    expanded = center + vectors * scale
    return np.round(expanded).astype(np.int32)


def _candidate_object_contour(image: np.ndarray, marker_corners: np.ndarray) -> tuple[np.ndarray | None, float]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    masks = [binary, cv2.bitwise_not(binary)]

    edges = cv2.Canny(blur, 45, 130)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    masks.append(edges)

    marker_poly = _expanded_marker_polygon(marker_corners)
    image_area = float(image.shape[0] * image.shape[1])
    marker_area = max(abs(float(cv2.contourArea(marker_corners.astype(np.float32)))), 1.0)

    best: np.ndarray | None = None
    best_score = -1.0
    best_quality = 0.0

    for raw in masks:
        mask = raw.copy()
        cv2.fillConvexPoly(mask, marker_poly, 0)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = abs(float(cv2.contourArea(contour)))
            if area < max(500.0, marker_area * 0.15):
                continue
            if area > image_area * 0.65:
                continue

            x, y, w, h = cv2.boundingRect(contour)
            if w <= 8 or h <= 8:
                continue
            touches = sum([
                x <= 2,
                y <= 2,
                x + w >= image.shape[1] - 2,
                y + h >= image.shape[0] - 2,
            ])
            if touches >= 2:
                continue

            rect = cv2.minAreaRect(contour)
            rw, rh = rect[1]
            if min(rw, rh) <= 0:
                continue
            elongation = max(rw, rh) / max(min(rw, rh), 1.0)
            hull = cv2.convexHull(contour)
            hull_area = max(abs(float(cv2.contourArea(hull))), 1.0)
            solidity = min(1.0, area / hull_area)

            # Grip-sleeve V0.3 targets elongated handheld objects. Favor a
            # coherent elongated contour while still allowing bowl/head geometry.
            score = area * (0.65 + 0.20 * min(elongation, 5.0) / 5.0 + 0.15 * solidity)
            if score > best_score:
                best = contour
                best_score = score
                area_quality = min(1.0, area / max(marker_area * 0.7, 1.0))
                shape_quality = min(1.0, 0.55 * solidity + 0.45 * min(elongation / 3.0, 1.0))
                best_quality = 0.5 * area_quality + 0.5 * shape_quality

    return best, max(0.0, min(1.0, best_quality))


def _homography_to_mm(marker_corners: np.ndarray) -> np.ndarray:
    size = float(settings.calibration_marker_size_mm)
    destination = np.array(
        [[0.0, 0.0], [size, 0.0], [size, size], [0.0, size]],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(marker_corners.astype(np.float32), destination)


def _principal_measurements(contour_mm: np.ndarray) -> dict:
    points = contour_mm.reshape(-1, 2).astype(np.float64)
    center = np.mean(points, axis=0)
    centered = points - center

    covariance = np.cov(centered.T)
    values, vectors = np.linalg.eigh(covariance)
    major = vectors[:, int(np.argmax(values))]
    minor = np.array([-major[1], major[0]])

    u = centered @ major
    v = centered @ minor
    length_mm = float(np.max(u) - np.min(u))
    overall_width_mm = float(np.max(v) - np.min(v))

    # Rasterize in a local, perspective-corrected millimetre coordinate system
    # and inspect the width profile along the long axis. For elongated utensils,
    # the sustained narrow region is a useful first estimate of the handle width.
    scale = 5.0  # pixels per millimetre in the local analysis raster
    local = np.column_stack([u - np.min(u), v - np.min(v)])
    width_px = max(32, int(math.ceil(length_mm * scale)) + 8)
    height_px = max(32, int(math.ceil(overall_width_mm * scale)) + 8)
    poly = np.round(local * scale + 4).astype(np.int32)
    canvas = np.zeros((height_px, width_px), dtype=np.uint8)
    cv2.fillPoly(canvas, [poly], 255)

    profile = np.count_nonzero(canvas, axis=0).astype(np.float64) / scale
    nonzero = np.flatnonzero(profile > 0)
    if len(nonzero) < 12:
        raise ValueError("Object contour is too small for a stable handle-width estimate.")

    start, end = int(nonzero[0]), int(nonzero[-1])
    span = end - start + 1
    margin = max(2, int(span * 0.08))
    usable = profile[start + margin : max(start + margin + 1, end - margin + 1)]
    usable = usable[usable > 0]
    if len(usable) < 8:
        usable = profile[nonzero]

    p20 = float(np.percentile(usable, 20))
    p50 = float(np.percentile(usable, 50))
    narrow = usable[(usable >= p20 * 0.75) & (usable <= p50)]
    interface_width_mm = float(np.median(narrow if len(narrow) else usable))

    threshold = max(interface_width_mm * 1.55, interface_width_mm + 2.0)
    narrow_mask = (profile > 0) & (profile <= threshold)
    longest = 0
    current = 0
    for value in narrow_mask[start : end + 1]:
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    available_length_mm = float(longest / scale)

    return {
        "object_length_mm": round(length_mm, 2),
        "object_overall_width_mm": round(overall_width_mm, 2),
        "interface_estimate_mm": round(interface_width_mm, 2),
        "available_length_mm": round(available_length_mm, 2),
    }


def _measure_bytes(data: bytes, view: str) -> dict:
    view = view.strip().lower()
    if view not in {"top", "side"}:
        return {
            "status": "error",
            "error": "view must be 'top' or 'side'.",
        }

    image = _decode_image(data)
    marker = _detect_reference_marker(image)
    if marker is None:
        return {
            "status": "recapture_required",
            "reason": "The Iyal.ai reference marker was not detected clearly.",
            "instructions": [
                "Place the printed Iyal.ai marker beside the object on the same flat plane.",
                "Keep the complete marker visible with good lighting and minimal glare.",
                "Retake the photo from above for a top view, or level with the object for a side view.",
            ],
        }

    contour, object_quality = _candidate_object_contour(image, marker.corners)
    if contour is None:
        return {
            "status": "recapture_required",
            "marker_detected": True,
            "reason": "The marker was found, but the object outline could not be isolated reliably.",
            "instructions": [
                "Use a plain background that contrasts with the object.",
                "Leave some space between the object and marker.",
                "Keep the full object visible and avoid strong shadows.",
            ],
        }

    H = _homography_to_mm(marker.corners)
    contour_mm = cv2.perspectiveTransform(contour.astype(np.float32), H)
    try:
        measured = _principal_measurements(contour_mm)
    except ValueError as exc:
        return {
            "status": "recapture_required",
            "marker_detected": True,
            "reason": str(exc),
        }

    interface_key = "interface_width_mm" if view == "top" else "interface_depth_mm"
    quality = max(0.0, min(1.0, 0.55 * marker.marker_quality + 0.45 * object_quality))

    result = {
        "status": "ok",
        "measurement_source": "calibrated_capture",
        "view": view,
        "marker": {
            "dictionary": settings.calibration_marker_dictionary,
            "id": settings.calibration_marker_id,
            "size_mm": settings.calibration_marker_size_mm,
        },
        interface_key: measured["interface_estimate_mm"],
        "object_length_mm": measured["object_length_mm"],
        "object_overall_width_mm": measured["object_overall_width_mm"],
        "available_length_mm": measured["available_length_mm"],
        "quality_score": round(quality, 3),
        "quality_note": (
            "Prototype capture-quality score; verify fit physically before relying on the design."
        ),
    }
    return result


def generate_calibration_marker_png(side_px: int = 1000) -> bytes:
    dictionary = _aruco_dictionary()
    marker = cv2.aruco.generateImageMarker(
        dictionary,
        settings.calibration_marker_id,
        int(side_px),
    )
    ok, encoded = cv2.imencode(".png", marker)
    if not ok:
        raise RuntimeError("Could not encode calibration marker PNG.")
    return encoded.tobytes()


def generate_calibration_marker_svg() -> str:
    """Return a printable SVG whose black marker square is exactly configured mm."""
    png = generate_calibration_marker_png()
    encoded = base64.b64encode(png).decode("ascii")
    size = float(settings.calibration_marker_size_mm)
    margin = 15.0
    footer = 24.0
    width = size + margin * 2
    height = size + margin * 2 + footer
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <image href="data:image/png;base64,{encoded}" x="{margin}" y="{margin}" width="{size}" height="{size}"/>
  <text x="{width/2}" y="{margin + size + 10}" text-anchor="middle" font-family="Arial, sans-serif" font-size="5">IYAL.AI CALIBRATION MARKER</text>
  <text x="{width/2}" y="{margin + size + 17}" text-anchor="middle" font-family="Arial, sans-serif" font-size="4">Black square = {size:g} mm × {size:g} mm · Marker ID {settings.calibration_marker_id}</text>
  <text x="{width/2}" y="{margin + size + 23}" text-anchor="middle" font-family="Arial, sans-serif" font-size="3.5">Print at 100% / Actual Size. Do not fit to page.</text>
</svg>'''


# ---------------------------------------------------------------------------
# V0.4 guided-capture measurement: A4/reference + Gemini target polygon
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferenceDetection:
    kind: str
    corners: np.ndarray  # ordered TL, TR, BR, BL in source-image pixels
    width_mm: float
    height_mm: float
    quality: float


def _order_quad_points(points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)
    return np.array(
        [
            pts[np.argmin(s)],      # top-left
            pts[np.argmin(diff)],   # top-right
            pts[np.argmax(s)],      # bottom-right
            pts[np.argmax(diff)],   # bottom-left
        ],
        dtype=np.float32,
    )


def _detect_a4_reference(image: np.ndarray) -> ReferenceDetection | None:
    """Detect a plain A4 sheet with all four corners visible.

    The detector deliberately validates the rectangle aspect ratio rather than
    assuming the largest bright region is paper. This is a capture aid, not a
    document scanner; difficult scenes should result in recapture rather than a
    questionable physical measurement.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    image_area = float(image.shape[0] * image.shape[1])

    candidates: list[np.ndarray] = []

    edges = cv2.Canny(blur, 45, 130)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates.extend(contours)

    # Also try a bright-surface mask. This helps when the paper edge is low
    # contrast but the sheet is brighter than the surrounding surface.
    _, bright = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    contours2, _ = cv2.findContours(bright, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates.extend(contours2)

    expected = float(settings.a4_long_side_mm / settings.a4_short_side_mm)
    best: ReferenceDetection | None = None
    best_score = -1.0

    for contour in candidates:
        area = abs(float(cv2.contourArea(contour)))
        area_ratio = area / max(image_area, 1.0)
        if area_ratio < 0.10 or area_ratio > 0.93:
            continue

        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue

        quad = _order_quad_points(approx.reshape(4, 2))
        tl, tr, br, bl = quad
        horizontal = (float(np.linalg.norm(tr - tl)) + float(np.linalg.norm(br - bl))) / 2.0
        vertical = (float(np.linalg.norm(bl - tl)) + float(np.linalg.norm(br - tr))) / 2.0
        short = max(min(horizontal, vertical), 1e-6)
        long = max(horizontal, vertical)
        ratio = long / short

        ratio_error = abs(ratio - expected) / expected
        if ratio_error > 0.18:
            continue

        rect = cv2.minAreaRect(quad)
        rw, rh = rect[1]
        rect_area = max(float(rw * rh), 1.0)
        rectangularity = min(1.0, area / rect_area)
        if rectangularity < 0.78:
            continue

        # Reject sheets whose corners are effectively outside the frame. We
        # want all four corners visible for stable perspective calibration.
        margin = max(4.0, min(image.shape[:2]) * 0.005)
        if any(
            x < margin or y < margin or x > image.shape[1] - margin or y > image.shape[0] - margin
            for x, y in quad
        ):
            continue

        aspect_quality = max(0.0, 1.0 - ratio_error / 0.18)
        size_quality = min(1.0, area_ratio / 0.35)
        quality = 0.45 * aspect_quality + 0.35 * rectangularity + 0.20 * size_quality

        if quality > best_score:
            if horizontal >= vertical:
                width_mm = float(settings.a4_long_side_mm)
                height_mm = float(settings.a4_short_side_mm)
            else:
                width_mm = float(settings.a4_short_side_mm)
                height_mm = float(settings.a4_long_side_mm)
            best = ReferenceDetection(
                kind="a4",
                corners=quad,
                width_mm=width_mm,
                height_mm=height_mm,
                quality=max(0.0, min(1.0, quality)),
            )
            best_score = quality

    return best


def _marker_reference(image: np.ndarray) -> ReferenceDetection | None:
    marker = _detect_reference_marker(image)
    if marker is None:
        return None
    quad = _order_quad_points(marker.corners)
    size = float(settings.calibration_marker_size_mm)
    return ReferenceDetection(
        kind="aruco",
        corners=quad,
        width_mm=size,
        height_mm=size,
        quality=marker.marker_quality,
    )


def _detect_measurement_reference(
    image: np.ndarray,
    reference_type: str = "a4",
) -> ReferenceDetection | None:
    mode = reference_type.strip().lower()
    if mode == "a4":
        return _detect_a4_reference(image)
    if mode in {"aruco", "marker"}:
        return _marker_reference(image)
    if mode == "auto":
        return _detect_a4_reference(image) or _marker_reference(image)
    raise ValueError("reference_type must be 'a4', 'aruco', or 'auto'.")


def _reference_homography_to_mm(reference: ReferenceDetection) -> np.ndarray:
    destination = np.array(
        [
            [0.0, 0.0],
            [reference.width_mm, 0.0],
            [reference.width_mm, reference.height_mm],
            [0.0, reference.height_mm],
        ],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(reference.corners.astype(np.float32), destination)


def _normalized_segmentation_to_pixels(
    image_shape: tuple[int, ...],
    box_2d: list[int],
    mask: list[list[int]],
) -> tuple[np.ndarray, str]:
    """Convert Gemini normalized box/polygon output to source-image pixels.

    Gemini's segmentation polygon is normalized inside its bounding box. If a
    polygon is unavailable we can fall back to the box rectangle, but the caller
    should surface that lower-precision mode to the user.
    """
    h, w = image_shape[:2]
    if len(box_2d) != 4:
        raise ValueError("Segmentation box_2d must have four values.")
    ymin, xmin, ymax, xmax = [max(0, min(1000, int(v))) for v in box_2d]
    if ymax <= ymin or xmax <= xmin:
        raise ValueError("Segmentation bounding box is invalid.")

    x0, x1 = xmin / 1000.0 * w, xmax / 1000.0 * w
    y0, y1 = ymin / 1000.0 * h, ymax / 1000.0 * h

    if mask and len(mask) >= 3:
        points = []
        for point in mask:
            if len(point) != 2:
                continue
            mx, my = point
            x = x0 + max(0, min(1000, float(mx))) / 1000.0 * (x1 - x0)
            y = y0 + max(0, min(1000, float(my))) / 1000.0 * (y1 - y0)
            points.append([x, y])
        if len(points) >= 3:
            return np.asarray(points, dtype=np.float32), "polygon"

    return np.asarray(
        [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32
    ), "bounding_box"


def _principal_polygon_dimensions(points_mm: np.ndarray) -> dict:
    points = np.asarray(points_mm, dtype=np.float64).reshape(-1, 2)
    if len(points) < 3:
        raise ValueError("Target segmentation does not contain enough points.")

    center = points.mean(axis=0)
    centered = points - center
    covariance = np.cov(centered.T)
    values, vectors = np.linalg.eigh(covariance)
    major_axis = vectors[:, int(np.argmax(values))]
    minor_axis = np.array([-major_axis[1], major_axis[0]])
    u = centered @ major_axis
    v = centered @ minor_axis

    major = float(np.max(u) - np.min(u))
    minor = float(np.max(v) - np.min(v))

    contour = points.astype(np.float32).reshape(-1, 1, 2)
    area = abs(float(cv2.contourArea(contour)))
    return {
        "major_mm": round(max(major, minor), 2),
        "minor_mm": round(min(major, minor), 2),
        "area_mm2": round(area, 2),
    }


def _measure_segmented_target_bytes(
    data: bytes,
    box_2d: list[int],
    mask: list[list[int]],
    reference_type: str = "a4",
) -> dict:
    """Measure a Gemini-localized target using deterministic reference geometry."""
    image = _decode_image(data)
    reference = _detect_measurement_reference(image, reference_type)
    if reference is None:
        if reference_type.strip().lower() == "a4":
            reason = "A complete A4 reference sheet could not be detected reliably."
            instructions = [
                "Place the complete object on a plain A4 sheet.",
                "Keep all four paper corners visible in the photo.",
                "Take the photo roughly perpendicular to the sheet and avoid strong shadows or glare.",
            ]
        else:
            reason = "The calibration marker could not be detected reliably."
            instructions = [
                "Keep the full marker and target region visible on the same plane.",
                "Avoid blur, glare, and severe camera angle.",
            ]
        return {
            "status": "recapture_required",
            "reason": reason,
            "instructions": instructions,
        }

    polygon_px, segmentation_mode = _normalized_segmentation_to_pixels(
        image.shape, box_2d, mask
    )

    # For A4 capture the target should lie on the reference surface. This is a
    # useful geometry sanity check before converting pixels to millimetres.
    if reference.kind == "a4":
        page_poly = reference.corners.astype(np.float32)
        inside = [
            cv2.pointPolygonTest(page_poly, (float(x), float(y)), False) >= 0
            for x, y in polygon_px
        ]
        if sum(inside) / max(len(inside), 1) < 0.75:
            return {
                "status": "recapture_required",
                "reference_detected": True,
                "reason": "The target region is not fully positioned on the A4 measurement surface.",
                "instructions": [
                    "Place the full target region inside the A4 sheet boundary.",
                    "Keep the object and sheet flat and take the photo again from above.",
                ],
            }

    H = _reference_homography_to_mm(reference)
    points_mm = cv2.perspectiveTransform(
        polygon_px.reshape(-1, 1, 2).astype(np.float32), H
    ).reshape(-1, 2)

    measured = _principal_polygon_dimensions(points_mm)
    quality = reference.quality
    if segmentation_mode == "bounding_box":
        quality *= 0.72

    return {
        "status": "ok",
        "measurement_source": "calibrated_capture",
        "reference_type": reference.kind,
        "reference_dimensions_mm": {
            "width": reference.width_mm,
            "height": reference.height_mm,
        },
        "segmentation_mode": segmentation_mode,
        "target_major_mm": measured["major_mm"],
        "target_minor_mm": measured["minor_mm"],
        "target_area_mm2": measured["area_mm2"],
        "quality_score": round(max(0.0, min(1.0, quality)), 3),
        "quality_note": (
            "Capture-quality score for prototype measurement; verify fit physically before relying on the design."
        ),
    }
