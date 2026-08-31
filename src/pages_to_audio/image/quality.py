"""Frame quality scorer — §3.1.2.

Components are independent and separately configurable; the score is NOT a probability.
Each component and the scorer version are persisted in Frame.quality_metrics (JSONB).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCORER_VERSION = "1.0"


@dataclass
class QualityComponents:
    blur_score: float  # variance of Laplacian (higher = sharper)
    glare_score: float  # 0-1, lower = more glare
    exposure_score: float  # 0-1, good exposure
    coverage_score: float  # 0-1, document coverage
    perspective_score: float  # 0-1, low distortion
    motion_score: float  # 0-1, low motion
    useful_area_score: float  # 0-1, useful pixel area
    aggregate: float  # weighted average
    scorer_version: str = SCORER_VERSION


WEIGHTS = {
    "blur": 0.30,
    "glare": 0.15,
    "exposure": 0.15,
    "coverage": 0.20,
    "perspective": 0.10,
    "motion": 0.05,
    "useful_area": 0.05,
}


def score_frame(image_bytes: bytes) -> QualityComponents:
    """
    Compute quality components for a frame.
    Falls back to safe defaults if PIL/CV2 unavailable.
    CPU-bound — must be called from a thread executor, never directly in async context.
    """
    try:
        blur, glare, exposure, coverage, perspective, motion, useful = _compute_components(
            image_bytes
        )
    except Exception:
        # Safe defaults — frame is usable but marked as degraded
        blur = glare = exposure = coverage = perspective = motion = useful = 0.5

    aggregate = (
        WEIGHTS["blur"] * blur
        + WEIGHTS["glare"] * glare
        + WEIGHTS["exposure"] * exposure
        + WEIGHTS["coverage"] * coverage
        + WEIGHTS["perspective"] * perspective
        + WEIGHTS["motion"] * motion
        + WEIGHTS["useful_area"] * useful
    )

    return QualityComponents(
        blur_score=blur,
        glare_score=glare,
        exposure_score=exposure,
        coverage_score=coverage,
        perspective_score=perspective,
        motion_score=motion,
        useful_area_score=useful,
        aggregate=aggregate,
    )


def quality_to_metrics(q: QualityComponents) -> dict[str, Any]:
    return {
        "blur_score": q.blur_score,
        "glare_score": q.glare_score,
        "exposure_score": q.exposure_score,
        "coverage_score": q.coverage_score,
        "perspective_score": q.perspective_score,
        "motion_score": q.motion_score,
        "useful_area_score": q.useful_area_score,
        "aggregate": q.aggregate,
        "scorer_version": q.scorer_version,
    }


def _compute_components(image_bytes: bytes) -> tuple[float, ...]:
    import io

    import numpy as np

    try:
        import cv2

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    except ImportError:
        from PIL import Image

        pil = Image.open(io.BytesIO(image_bytes)).convert("L")
        import numpy as np

        gray = np.array(pil, dtype=np.uint8)
        img = gray

    h, w = gray.shape[:2]

    # Blur — variance of Laplacian (normalized to 0-1 with soft cap at 500)
    import cv2 as _cv2

    lap_var = float(_cv2.Laplacian(gray, _cv2.CV_64F).var())
    blur = min(lap_var / 500.0, 1.0)

    # Glare — fraction of overexposed pixels
    _, thresh = _cv2.threshold(gray, 250, 255, _cv2.THRESH_BINARY)
    glare_frac = thresh.sum() / 255 / (h * w)
    glare = max(0.0, 1.0 - glare_frac * 10)

    # Exposure — histogram spread
    hist = _cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist_norm = hist / hist.sum()
    mean_val = float(np.sum(np.arange(256) * hist_norm.flatten()))
    exposure = 1.0 - abs(mean_val - 128) / 128

    # Coverage and perspective — placeholder based on edge density
    edges = _cv2.Canny(gray, 50, 150)
    edge_density = edges.sum() / 255 / (h * w)
    coverage = min(edge_density * 5, 1.0)
    perspective = max(0.0, 1.0 - edge_density * 2)

    # Motion — placeholder (single frame, no prior reference)
    motion = 0.8

    # Useful area
    useful = min(coverage * 1.2, 1.0)

    return blur, glare, exposure, coverage, perspective, motion, useful
