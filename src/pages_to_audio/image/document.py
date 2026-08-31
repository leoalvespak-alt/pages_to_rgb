"""Document detection — presence, boundaries, orientation — §15.3, §15.6."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DocumentDetectionResult:
    document_present: bool
    confidence: float
    estimated_angle_degrees: float
    bounding_box: dict[str, float] | None


def detect_document(image_path: Path) -> DocumentDetectionResult:
    """
    Detect presence and boundaries of an exam document in a frame.
    CPU-bound: must run in executor.
    """
    try:
        import cv2
        import numpy as np  # noqa: F401

        img = cv2.imread(str(image_path))
        if img is None:
            return DocumentDetectionResult(False, 0.0, 0.0, None)

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 75, 200)
        contours, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return DocumentDetectionResult(False, 0.0, 0.0, None)

        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        frame_area = float(h * w)
        coverage = area / frame_area

        # A document should cover at least 20% of the frame
        if coverage < 0.20:
            return DocumentDetectionResult(False, float(coverage), 0.0, None)

        rect = cv2.minAreaRect(largest)
        angle = float(rect[2])
        x, y, rw, rh = cv2.boundingRect(largest)

        return DocumentDetectionResult(
            document_present=True,
            confidence=min(float(coverage), 1.0),
            estimated_angle_degrees=angle,
            bounding_box={"x": float(x), "y": float(y), "width": float(rw), "height": float(rh)},
        )

    except ImportError:
        # Fallback without OpenCV: assume document present
        return DocumentDetectionResult(True, 0.5, 0.0, None)
    except Exception:
        return DocumentDetectionResult(False, 0.0, 0.0, None)
