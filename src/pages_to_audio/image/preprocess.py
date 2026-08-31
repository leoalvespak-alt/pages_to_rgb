"""Image preprocessing pipeline — §18.2, Invariant 8.

Each operation is isolated and optional. ORIGINAL is never modified.
All operations are synchronous (OpenCV); must run in executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class PreprocessOp(StrEnum):
    ORIENTATION = "corrected_orientation"
    PERSPECTIVE = "perspective"
    CLAHE = "clahe"
    DENOISE = "denoise"
    SHARPEN = "sharpen"
    THRESHOLD = "threshold"


@dataclass
class PreprocessResult:
    op: PreprocessOp
    output_path: Path
    success: bool
    error: str | None = None


@dataclass
class PreprocessRequest:
    input_path: Path
    ops: list[PreprocessOp] = field(default_factory=list)
    output_dir: Path | None = None

    def __post_init__(self) -> None:
        if not self.ops:
            self.ops = list(PreprocessOp)


def _load_image(path: Path) -> np.ndarray:
    try:
        import cv2

        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"Could not read image: {path}")
        return img
    except ImportError:
        import numpy as np
        from PIL import Image

        return np.array(Image.open(path).convert("RGB"))


def _save_image(img: np.ndarray, path: Path) -> None:
    try:
        import cv2

        cv2.imwrite(str(path), img)
    except ImportError:
        from PIL import Image

        Image.fromarray(img).save(path)


def apply_orientation(img: np.ndarray) -> np.ndarray:
    """Detect and correct rotation via Hough transform (simplified)."""
    try:
        import cv2
        import numpy as np

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 200)
        if lines is None:
            return img
        angles = [line[0][1] for line in lines[:10]]
        median_angle = float(np.median(angles)) * 180 / np.pi - 90
        if abs(median_angle) < 1.0:
            return img
        h, w = img.shape[:2]
        rot_matrix = cv2.getRotationMatrix2D((w // 2, h // 2), median_angle, 1.0)
        return cv2.warpAffine(
            img,
            rot_matrix,
            (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
    except Exception:
        return img


def apply_perspective(img: np.ndarray) -> np.ndarray:
    """Attempt basic perspective correction via contour detection."""
    try:
        import cv2

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 75, 200)
        contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
        for c in contours:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            if len(approx) == 4:
                # Found a quadrilateral — perspective correction would go here
                # Simplified: return original (full warp requires ordered points)
                return img
        return img
    except Exception:
        return img


def apply_clahe(img: np.ndarray) -> np.ndarray:
    """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)."""
    try:
        import cv2

        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l_channel)
        merged = cv2.merge([cl, a, b])
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
    except Exception:
        return img


def apply_denoise(img: np.ndarray) -> np.ndarray:
    try:
        import cv2

        return cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
    except Exception:
        return img


def apply_sharpen(img: np.ndarray) -> np.ndarray:
    try:
        import cv2
        import numpy as np

        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        return cv2.filter2D(img, -1, kernel)
    except Exception:
        return img


def apply_threshold(img: np.ndarray) -> np.ndarray:
    try:
        import cv2

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)
    except Exception:
        return img


_OP_FUNCS = {
    PreprocessOp.ORIENTATION: apply_orientation,
    PreprocessOp.PERSPECTIVE: apply_perspective,
    PreprocessOp.CLAHE: apply_clahe,
    PreprocessOp.DENOISE: apply_denoise,
    PreprocessOp.SHARPEN: apply_sharpen,
    PreprocessOp.THRESHOLD: apply_threshold,
}


def preprocess_image(request: PreprocessRequest) -> list[PreprocessResult]:
    """
    Apply requested preprocessing operations synchronously.
    Each op writes a separate output file (ORIGINAL untouched, §18.1/Invariant 8).
    Must be run in executor — never call from event loop directly.
    """
    output_dir = request.output_dir or request.input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    img = _load_image(request.input_path)
    results: list[PreprocessResult] = []

    for op in request.ops:
        func = _OP_FUNCS[op]
        out_path = output_dir / f"{op.value}.jpg"
        try:
            processed = func(img)
            _save_image(processed, out_path)
            results.append(PreprocessResult(op=op, output_path=out_path, success=True))
        except Exception as exc:
            results.append(
                PreprocessResult(op=op, output_path=out_path, success=False, error=str(exc))
            )

    return results
