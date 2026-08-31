"""Region crop utilities — §18.2, §5.2.4."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CropRegion:
    x: float
    y: float
    width: float
    height: float
    label: str = ""


@dataclass
class CropResult:
    output_path: Path
    region: CropRegion
    success: bool
    error: str | None = None


def crop_region(image_path: Path, region: CropRegion, output_path: Path) -> CropResult:
    """
    Crop a region from an image. Coordinates are absolute pixels.
    Must run in executor — CPU-bound.
    """
    try:
        import cv2

        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        h, w = img.shape[:2]
        x1 = max(0, int(region.x))
        y1 = max(0, int(region.y))
        x2 = min(w, int(region.x + region.width))
        y2 = min(h, int(region.y + region.height))

        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"Invalid crop region: {region}")

        cropped = img[y1:y2, x1:x2]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), cropped)
        return CropResult(output_path=output_path, region=region, success=True)

    except ImportError:
        from PIL import Image

        img_pil = Image.open(image_path)
        w, h = img_pil.size
        x1 = max(0, int(region.x))
        y1 = max(0, int(region.y))
        x2 = min(w, int(region.x + region.width))
        y2 = min(h, int(region.y + region.height))
        cropped = img_pil.crop((x1, y1, x2, y2))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(output_path)
        return CropResult(output_path=output_path, region=region, success=True)

    except Exception as exc:
        return CropResult(output_path=output_path, region=region, success=False, error=str(exc))


def crop_question_region(
    image_path: Path,
    region: CropRegion,
    output_dir: Path,
    question_number: int,
) -> CropResult:
    """Crop a question region — artifact_type = question_crop (§8.8)."""
    out = output_dir / f"question_{question_number:03d}.jpg"
    return crop_region(image_path, region, out)


def crop_media_region(
    image_path: Path,
    region: CropRegion,
    output_dir: Path,
    media_id: str,
) -> CropResult:
    """Crop an embedded media region — artifact_type = media_crop (§8.8)."""
    out = output_dir / f"media_{media_id}.jpg"
    return crop_region(image_path, region, out)
