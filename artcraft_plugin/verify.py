"""Image inspection and post-edit verification helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from PIL import Image, ImageChops


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_image(path_str: str) -> Dict[str, Any]:
    """Inspect an image file's format, dimensions, mode, DPI, and SHA-256."""
    path = Path(path_str).expanduser()
    if not path.is_file():
        return {"exists": False, "path": str(path), "error": "File does not exist"}

    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            dpi = img.info.get("dpi")
            return {
                "exists": True,
                "valid": True,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "format": img.format,
                "mode": img.mode,
                "width": img.width,
                "height": img.height,
                "dpi": list(dpi) if isinstance(dpi, tuple) else dpi,
            }
    except Exception as exc:
        return {
            "exists": True,
            "valid": False,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "error": f"Invalid or unreadable image: {exc}",
        }


def _count_changed_pixels(img_a: Image.Image, img_b: Image.Image) -> int:
    """Count pixels that differ between two same-size images."""
    a_rgba = img_a.convert("RGBA")
    b_rgba = img_b.convert("RGBA")
    diff = ImageChops.difference(a_rgba, b_rgba)
    # Collapse RGBA channels per pixel: any non-zero channel marks the pixel changed.
    raw = diff.tobytes()
    changed = 0
    for idx in range(0, len(raw), 4):
        if raw[idx] or raw[idx + 1] or raw[idx + 2] or raw[idx + 3]:
            changed += 1
    return changed


def _validate_region(region: Sequence[int], width: int, height: int) -> tuple[int, int, int, int]:
    """Validate an [x, y, w, h] region and convert to PIL crop box (x0, y0, x1, y1)."""
    if len(region) != 4:
        raise ValueError("region must be [x, y, width, height]")
    x, y, w, h = (int(v) for v in region)
    if w <= 0 or h <= 0:
        raise ValueError("region width and height must be positive")
    if x < 0 or y < 0 or x + w > width or y + h > height:
        raise ValueError(
            f"region {[x, y, w, h]} is outside image bounds ({width}x{height})"
        )
    return (x, y, x + w, y + h)


def verify_edit(
    input_path_str: str,
    output_path_str: str,
    *,
    expected_width: Optional[int] = None,
    expected_height: Optional[int] = None,
    region: Optional[Sequence[int]] = None,
    require_pixel_change: bool = True,
) -> Dict[str, Any]:
    """Verify an edited image against its source input and optional constraints."""
    in_info = inspect_image(input_path_str)
    if not in_info.get("valid"):
        return {
            "passed": False,
            "reason": f"invalid_input: {in_info.get('error', 'unreadable input')}",
            "input": in_info,
        }

    out_info = inspect_image(output_path_str)
    if not out_info.get("valid"):
        return {
            "passed": False,
            "reason": f"invalid_output: {out_info.get('error', 'unreadable output')}",
            "input": in_info,
            "output": out_info,
        }

    out_w, out_h = out_info["width"], out_info["height"]
    if expected_width is not None and out_w != expected_width:
        return {
            "passed": False,
            "reason": f"dimension_mismatch: expected width {expected_width}, got {out_w}",
            "input": in_info,
            "output": out_info,
        }
    if expected_height is not None and out_h != expected_height:
        return {
            "passed": False,
            "reason": f"dimension_mismatch: expected height {expected_height}, got {out_h}",
            "input": in_info,
            "output": out_info,
        }

    byte_identical = in_info["sha256"] == out_info["sha256"]
    same_dimensions = (in_info["width"], in_info["height"]) == (out_w, out_h)

    pixel_diff: Dict[str, Any] = {"same_dimensions": same_dimensions}
    if same_dimensions:
        with Image.open(in_info["path"]) as img_in, Image.open(out_info["path"]) as img_out:
            total_pixels = img_in.width * img_in.height
            changed_pixels = _count_changed_pixels(img_in, img_out)
            pixel_diff.update(
                {
                    "changed_pixels": changed_pixels,
                    "total_pixels": total_pixels,
                    "changed_ratio": round(changed_pixels / total_pixels, 6) if total_pixels else 0.0,
                }
            )
            if region is not None:
                box = _validate_region(region, img_in.width, img_in.height)
                reg_in = img_in.crop(box)
                reg_out = img_out.crop(box)
                reg_total = reg_in.width * reg_in.height
                reg_changed = _count_changed_pixels(reg_in, reg_out)
                pixel_diff["region"] = {
                    "box": list(region),
                    "changed_pixels": reg_changed,
                    "total_pixels": reg_total,
                    "changed_ratio": round(reg_changed / reg_total, 6) if reg_total else 0.0,
                }

        if require_pixel_change and pixel_diff["changed_pixels"] == 0:
            return {
                "passed": False,
                "reason": "no_op_edit: output is pixel-identical to input",
                "byte_identical": byte_identical,
                "pixel_diff": pixel_diff,
                "input": in_info,
                "output": out_info,
            }

        if require_pixel_change and region is not None:
            if pixel_diff["region"]["changed_pixels"] == 0:
                return {
                    "passed": False,
                    "reason": "no_op_in_region: target region has zero changed pixels",
                    "byte_identical": byte_identical,
                    "pixel_diff": pixel_diff,
                    "input": in_info,
                    "output": out_info,
                }
    elif require_pixel_change and byte_identical:
        return {
            "passed": False,
            "reason": "no_op_edit: output is byte-identical to input",
            "byte_identical": True,
            "pixel_diff": pixel_diff,
            "input": in_info,
            "output": out_info,
        }

    return {
        "passed": True,
        "reason": "ok",
        "byte_identical": byte_identical,
        "pixel_diff": pixel_diff,
        "input": in_info,
        "output": out_info,
    }
