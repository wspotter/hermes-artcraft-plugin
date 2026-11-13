"""Review package builder and quality-trap detection for ArtCraft plugin.

Builds structured review packages: whole-photo before/after previews,
native-resolution repaired-area crops, source/output SHA-256 hashes,
mechanical checks (dimensions, aspect ratio, format, ICC profile), and
automated mechanical/heuristic flags to catch intentionally poor results:
  - Untouched scratch / no-op: 0 changed pixels in target region or globally.
  - Unwanted crop: aspect ratio or framing changed unexpectedly without authorization.
  - Smeared repair: excessive local variance/detail collapse in the repaired region
    compared to surrounding reference texture (>80-90% variance drop).
Supports bounded retry tracking (retry_count, max_retries, last_checkpoint_path).
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageChops, ImageStat

try:
    import numpy as np
except ImportError:
    np = None

from .inspect import determine_aspect_ratio, determine_orientation
from .verify import _count_changed_pixels, _validate_region, inspect_image, sha256_file


def parse_aspect_ratio(val: Union[float, int, str, None]) -> Optional[float]:
    """Parse aspect ratio from float, int, or ratio string (e.g. '4:5', '16:9')."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else None
    if isinstance(val, str):
        val_str = val.strip()
        if ":" in val_str:
            parts = val_str.split(":", 1)
            try:
                num, den = float(parts[0]), float(parts[1])
                return num / den if den > 0 else None
            except ValueError:
                return None
        elif "/" in val_str:
            parts = val_str.split("/", 1)
            try:
                num, den = float(parts[0]), float(parts[1])
                return num / den if den > 0 else None
            except ValueError:
                return None
        try:
            parsed = float(val_str)
            return parsed if parsed > 0 else None
        except ValueError:
            return None
    return None


def calculate_texture_metrics(
    crop_img: Image.Image,
    repaired_box_in_crop: Tuple[int, int, int, int],
) -> Dict[str, Any]:
    """Calculate intensity variance and Laplacian edge variance for repaired patch vs surrounding.

    Args:
        crop_img: Grayscale or RGB PIL Image of the context crop containing the repair.
        repaired_box_in_crop: (rx0, ry0, rx1, ry1) coordinates of repaired box within crop_img.

    Returns:
        Dict with repaired_variance, surrounding_variance, variance_drop_pct,
        repaired_laplacian_var, surrounding_laplacian_var, laplacian_drop_pct.
    """
    rx0, ry0, rx1, ry1 = repaired_box_in_crop
    rx0 = max(0, min(crop_img.width, rx0))
    rx1 = max(0, min(crop_img.width, rx1))
    ry0 = max(0, min(crop_img.height, ry0))
    ry1 = max(0, min(crop_img.height, ry1))

    # Ensure grayscale luminance
    if crop_img.mode != "L":
        gray = crop_img.convert("L")
    else:
        gray = crop_img

    if np is not None:
        arr = np.asarray(gray, dtype=np.float64)
        rep_pixels = arr[ry0:ry1, rx0:rx1]

        mask = np.ones(arr.shape, dtype=bool)
        mask[ry0:ry1, rx0:rx1] = False
        sur_pixels = arr[mask]

        var_rep = float(np.var(rep_pixels)) if rep_pixels.size > 0 else 0.0
        var_sur = float(np.var(sur_pixels)) if sur_pixels.size > 0 else 0.0

        # Laplacian edge variance
        if arr.shape[0] >= 3 and arr.shape[1] >= 3:
            lap = (
                arr[2:, 1:-1]
                + arr[:-2, 1:-1]
                + arr[1:-1, 2:]
                + arr[1:-1, :-2]
                - 4.0 * arr[1:-1, 1:-1]
            )
            # Offset by 1 due to slice boundary
            l_ry0 = max(0, ry0 - 1)
            l_ry1 = max(0, min(lap.shape[0], ry1 - 1))
            l_rx0 = max(0, rx0 - 1)
            l_rx1 = max(0, min(lap.shape[1], rx1 - 1))

            rep_lap = lap[l_ry0:l_ry1, l_rx0:l_rx1]
            lap_mask = np.ones(lap.shape, dtype=bool)
            lap_mask[l_ry0:l_ry1, l_rx0:l_rx1] = False
            sur_lap = lap[lap_mask]

            lap_var_rep = float(np.var(rep_lap)) if rep_lap.size > 0 else 0.0
            lap_var_sur = float(np.var(sur_lap)) if sur_lap.size > 0 else 0.0
        else:
            lap_var_rep = 0.0
            lap_var_sur = 0.0
    else:
        # Fallback using PIL ImageStat if numpy unavailable
        rep_crop = gray.crop((rx0, ry0, rx1, ry1))
        rep_stat = ImageStat.Stat(rep_crop)
        full_stat = ImageStat.Stat(gray)
        var_rep = float(rep_stat.var[0]) if rep_stat.var else 0.0
        var_sur = float(full_stat.var[0]) if full_stat.var else 0.0
        lap_var_rep = 0.0
        lap_var_sur = 0.0

    var_drop_pct = (
        round((1.0 - (var_rep / var_sur)) * 100.0, 1)
        if var_sur > 1e-4
        else 0.0
    )
    lap_drop_pct = (
        round((1.0 - (lap_var_rep / lap_var_sur)) * 100.0, 1)
        if lap_var_sur > 1e-4
        else 0.0
    )

    return {
        "repaired_variance": round(var_rep, 2),
        "surrounding_variance": round(var_sur, 2),
        "variance_drop_pct": var_drop_pct,
        "repaired_laplacian_var": round(lap_var_rep, 2),
        "surrounding_laplacian_var": round(lap_var_sur, 2),
        "laplacian_drop_pct": lap_drop_pct,
    }


def generate_preview(img: Image.Image, out_path: Path, max_dim: int = 1024) -> Tuple[int, int]:
    """Save a downscaled preview of img into out_path, preserving aspect ratio."""
    w, h = img.width, img.height
    scale = min(1.0, max_dim / max(w, h))
    preview_w = max(1, int(round(w * scale)))
    preview_h = max(1, int(round(h * scale)))

    if scale < 1.0:
        preview_img = img.resize((preview_w, preview_h), resample=Image.Resampling.LANCZOS)
    else:
        preview_img = img.copy()

    preview_img.save(out_path, format="PNG")
    return (preview_w, preview_h)


def build_review_package(
    source_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    regions: Optional[Sequence[Sequence[int]]] = None,
    region: Optional[Sequence[int]] = None,
    working_dir: Optional[Union[str, Path]] = None,
    max_preview_dimension: int = 1024,
    crop_size: int = 256,
    expected_aspect: Optional[Union[float, str]] = None,
    preserve_framing: bool = True,
    retry_count: int = 0,
    max_retries: int = 3,
    last_checkpoint_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Build a structured review package for an image edit and test for defect traps.

    Checks:
      1. Whole-photo before/after previews
      2. Native-resolution repaired-area crops (with surrounding context)
      3. Source and output SHA-256 hashes
      4. Mechanical checks (dimensions, aspect ratio, format, ICC)
      5. Automated defect detection:
         - Untouched scratch / no-op: 0 changed pixels in repair region or globally
         - Unwanted crop: aspect ratio or framing changed unexpectedly
         - Smeared repair: >80-90% variance collapse compared to surrounding texture
      6. Bounded retry tracking: retry_count, max_retries, last_checkpoint_path
    """
    src_p = Path(source_path).expanduser().resolve()
    out_p = Path(output_path).expanduser().resolve()

    if not src_p.is_file():
        return {
            "ok": False,
            "passed": False,
            "error": f"Source image does not exist: {src_p}",
        }
    if not out_p.is_file():
        return {
            "ok": False,
            "passed": False,
            "error": f"Output image does not exist: {out_p}",
        }

    # Normalize regions
    norm_regions: List[Tuple[int, int, int, int]] = []
    if region is not None:
        norm_regions.append(tuple(int(v) for v in region))
    if regions is not None:
        for r in regions:
            norm_regions.append(tuple(int(v) for v in r))

    # Setup working directory
    if working_dir:
        work_dir = Path(working_dir).expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="artcraft_review_"))

    flags: List[Dict[str, Any]] = []
    concerns: List[str] = []

    # Inspect files
    src_info = inspect_image(str(src_p))
    out_info = inspect_image(str(out_p))

    if not src_info.get("valid"):
        return {"ok": False, "passed": False, "error": f"Invalid source image: {src_info.get('error')}"}
    if not out_info.get("valid"):
        return {"ok": False, "passed": False, "error": f"Invalid output image: {out_info.get('error')}"}

    src_w, src_h = src_info["width"], src_info["height"]
    out_w, out_h = out_info["width"], out_info["height"]

    src_aspect_info = determine_aspect_ratio(src_w, src_h)
    out_aspect_info = determine_aspect_ratio(out_w, out_h)
    src_ratio = round(src_w / src_h, 4) if src_h else 0.0
    out_ratio = round(out_w / out_h, 4) if out_h else 0.0

    # Open images for processing
    with Image.open(src_p) as s_img, Image.open(out_p) as o_img:
        s_img.load()
        o_img.load()

        # Generate whole-photo previews
        src_preview_file = work_dir / "preview_source.png"
        out_preview_file = work_dir / "preview_output.png"
        src_prev_dim = generate_preview(s_img, src_preview_file, max_preview_dimension)
        out_prev_dim = generate_preview(o_img, out_preview_file, max_preview_dimension)

        # Total changed pixels calculation
        same_dims = (src_w == out_w and src_h == out_h)
        if same_dims:
            total_changed_pixels = _count_changed_pixels(s_img, o_img)
            total_pixels = src_w * src_h
            changed_pixel_pct = round((total_changed_pixels / total_pixels) * 100.0, 4)
        else:
            total_changed_pixels = 0
            total_pixels = src_w * src_h
            changed_pixel_pct = 0.0

        # Quality Trap 1: Untouched scratch / no-op globally
        if same_dims and total_changed_pixels == 0:
            flag = {
                "id": "untouched_scratch",
                "severity": "error",
                "message": "Untouched scratch / no-op: Zero changed pixels detected between source and output.",
                "details": {"total_changed_pixels": 0},
            }
            flags.append(flag)
            concerns.append(flag["message"])

        # Quality Trap 2: Unwanted crop / framing change
        parsed_expected_aspect = parse_aspect_ratio(expected_aspect)
        if parsed_expected_aspect is not None:
            if abs(out_ratio - parsed_expected_aspect) > 0.005:
                flag = {
                    "id": "unwanted_crop",
                    "severity": "error",
                    "message": (
                        f"Unwanted crop: Output aspect ratio ({out_ratio:.4f}, {out_aspect_info.get('standard_label')}) "
                        f"does not match expected aspect ratio ({parsed_expected_aspect:.4f})."
                    ),
                    "details": {
                        "expected_aspect": expected_aspect,
                        "expected_ratio": parsed_expected_aspect,
                        "output_aspect": out_ratio,
                    },
                }
                flags.append(flag)
                concerns.append(flag["message"])
        elif preserve_framing:
            if abs(out_ratio - src_ratio) > 0.005:
                flag = {
                    "id": "unwanted_crop",
                    "severity": "error",
                    "message": (
                        f"Unwanted crop: Framing changed from {src_ratio:.4f} ({src_aspect_info.get('standard_label')}) "
                        f"to {out_ratio:.4f} ({out_aspect_info.get('standard_label')}) when preserve_framing was requested."
                    ),
                    "details": {
                        "source_aspect": src_ratio,
                        "output_aspect": out_ratio,
                        "source_dimensions": [src_w, src_h],
                        "output_dimensions": [out_w, out_h],
                    },
                }
                flags.append(flag)
                concerns.append(flag["message"])

        # Mechanical check for dimension mismatch if framing preserved
        if preserve_framing and not same_dims and not any(f["id"] == "unwanted_crop" for f in flags):
            flag = {
                "id": "dimension_mismatch",
                "severity": "warning",
                "message": f"Dimensions changed from {src_w}x{src_h} to {out_w}x{out_h}.",
                "details": {"source": [src_w, src_h], "output": [out_w, out_h]},
            }
            flags.append(flag)
            concerns.append(flag["message"])

        # Native-resolution repaired-area crops & quality trap 3 (smeared repair / untouched scratch per-region)
        crops_data: List[Dict[str, Any]] = []

        # If no regions specified but pixels changed on same-size image, auto-detect changed region
        effective_regions = list(norm_regions)
        if not effective_regions and same_dims and total_changed_pixels > 0:
            diff_box = ImageChops.difference(s_img.convert("RGBA"), o_img.convert("RGBA")).getbbox()
            if diff_box:
                dx0, dy0, dx1, dy1 = diff_box
                effective_regions.append((dx0, dy0, dx1 - dx0, dy1 - dy0))

        for idx, reg in enumerate(effective_regions):
            rx, ry, rw, rh = reg
            if rw <= 0 or rh <= 0:
                continue

            # Validate region bounds in source
            if rx < 0 or ry < 0 or rx + rw > src_w or ry + rh > src_h:
                flag = {
                    "id": "invalid_region",
                    "severity": "error",
                    "message": f"Region {[rx, ry, rw, rh]} exceeds source image bounds ({src_w}x{src_h}).",
                    "details": {"region": [rx, ry, rw, rh]},
                }
                flags.append(flag)
                concerns.append(flag["message"])
                continue

            # Determine context crop window around region
            pad = max(16, min(rw, rh))
            target_crop_dim = max(crop_size, max(rw + pad * 2, rh + pad * 2))

            cx = rx + rw // 2
            cy = ry + rh // 2
            half_w = target_crop_dim // 2
            half_h = target_crop_dim // 2

            crop_x0 = max(0, min(src_w - target_crop_dim, cx - half_w)) if src_w >= target_crop_dim else 0
            crop_y0 = max(0, min(src_h - target_crop_dim, cy - half_h)) if src_h >= target_crop_dim else 0
            crop_x1 = min(src_w, crop_x0 + target_crop_dim)
            crop_y1 = min(src_h, crop_y0 + target_crop_dim)

            # Native 1:1 crops
            src_crop = s_img.crop((crop_x0, crop_y0, crop_x1, crop_y1))

            # Repaired coordinates relative to crop
            rel_rx0 = rx - crop_x0
            rel_ry0 = ry - crop_y0
            rel_rx1 = rel_rx0 + rw
            rel_ry1 = rel_ry0 + rh

            src_crop_path = work_dir / f"crop_{idx}_source.png"
            src_crop.save(src_crop_path, format="PNG")

            out_crop_path: Optional[Path] = None
            changed_in_region = 0
            texture_metrics: Dict[str, Any] = {}

            if same_dims:
                out_crop = o_img.crop((crop_x0, crop_y0, crop_x1, crop_y1))
                out_crop_path = work_dir / f"crop_{idx}_output.png"
                out_crop.save(out_crop_path, format="PNG")

                # Exact region crops for pixel diff
                s_exact = s_img.crop((rx, ry, rx + rw, ry + rh))
                o_exact = o_img.crop((rx, ry, rx + rw, ry + rh))
                changed_in_region = _count_changed_pixels(s_exact, o_exact)

                # Quality Trap 1 (Per-region untouched scratch)
                if changed_in_region == 0:
                    untouched_flag = {
                        "id": "untouched_scratch",
                        "severity": "error",
                        "message": (
                            f"Untouched scratch / no-op: Zero changed pixels in target repair region {[rx, ry, rw, rh]}."
                        ),
                        "details": {"region": [rx, ry, rw, rh], "changed_pixels": 0},
                    }
                    if not any(f["id"] == "untouched_scratch" and f.get("details", {}).get("region") == [rx, ry, rw, rh] for f in flags):
                        flags.append(untouched_flag)
                        concerns.append(untouched_flag["message"])

                # Quality Trap 3: Smeared repair (variance / detail collapse)
                texture_metrics = calculate_texture_metrics(
                    out_crop,
                    (rel_rx0, rel_ry0, rel_rx1, rel_ry1),
                )

                sur_var = texture_metrics["surrounding_variance"]
                sur_lap = texture_metrics["surrounding_laplacian_var"]
                var_drop = texture_metrics["variance_drop_pct"]
                lap_drop = texture_metrics["laplacian_drop_pct"]

                # If surrounding texture has authentic grain/detail and repair region collapsed >80%
                is_textured_surround = (sur_lap >= 10.0 or sur_var >= 12.0)
                is_severe_collapse = (lap_drop >= 80.0 or var_drop >= 85.0)

                if is_textured_surround and is_severe_collapse:
                    smear_flag = {
                        "id": "smeared_repair",
                        "severity": "error",
                        "message": (
                            f"Smeared repair: Excessive texture variance collapse in region {[rx, ry, rw, rh]} "
                            f"({max(var_drop, lap_drop):.1f}% drop). Repair appears blurred or smeared "
                            "relative to surrounding reference texture."
                        ),
                        "details": {
                            "region": [rx, ry, rw, rh],
                            **texture_metrics,
                        },
                    }
                    flags.append(smear_flag)
                    concerns.append(smear_flag["message"])

            crops_data.append({
                "region": [rx, ry, rw, rh],
                "crop_box": [crop_x0, crop_y0, crop_x1, crop_y1],
                "source_crop_path": str(src_crop_path),
                "output_crop_path": str(out_crop_path) if out_crop_path else None,
                "changed_pixels": changed_in_region,
                "changed_pct": round((changed_in_region / (rw * rh)) * 100.0, 2) if rw * rh else 0.0,
                "texture_metrics": texture_metrics,
            })

    # Mechanical checks summary
    mechanical_checks = {
        "dimensions_match": same_dims,
        "aspect_ratio_match": abs(src_ratio - out_ratio) <= 0.005,
        "format_match": src_info.get("format") == out_info.get("format"),
        "color_mode_match": src_info.get("mode") == out_info.get("mode"),
        "icc_profile_preserved": src_info.get("has_icc_profile") == out_info.get("has_icc_profile"),
        "total_changed_pixels": total_changed_pixels,
        "total_pixel_count": total_pixels,
        "changed_pixel_pct": changed_pixel_pct,
        "is_identical": (src_info.get("sha256") == out_info.get("sha256")),
    }

    # Format / Mode / ICC concerns
    if not mechanical_checks["format_match"]:
        concerns.append(f"Format changed from {src_info.get('format')} to {out_info.get('format')}.")
    if not mechanical_checks["color_mode_match"]:
        concerns.append(f"Color mode changed from {src_info.get('mode')} to {out_info.get('mode')}.")
    if src_info.get("has_icc_profile") and not out_info.get("has_icc_profile"):
        flag = {
            "id": "icc_dropped",
            "severity": "warning",
            "message": "Source embedded ICC profile was lost in output.",
            "details": {},
        }
        flags.append(flag)
        concerns.append(flag["message"])

    # Bounded retry tracking
    has_blocking_errors = any(f.get("severity") == "error" for f in flags)
    passed = (not has_blocking_errors) and (not mechanical_checks["is_identical"])

    retries_exhausted = (retry_count >= max_retries)
    can_retry = (not passed) and (not retries_exhausted)

    if passed:
        suggested_action = "approve"
    elif can_retry:
        suggested_action = "retry_from_checkpoint"
    else:
        suggested_action = "escalate_to_operator"

    retry_tracking = {
        "retry_count": retry_count,
        "max_retries": max_retries,
        "retries_exhausted": retries_exhausted,
        "can_retry": can_retry,
        "last_checkpoint_path": str(last_checkpoint_path) if last_checkpoint_path else None,
        "suggested_action": suggested_action,
    }

    if passed:
        summary = (
            f"Review passed: All mechanical checks passed ({out_w}x{out_h}, {out_info.get('format')}). "
            f"Repaired regions verified with authentic texture and no unwanted cropping."
        )
    else:
        error_names = ", ".join(sorted(list({f["id"] for f in flags}))) or "Unverified edit"
        summary = f"Review rejected: Quality traps or defects detected ({error_names})."

    return {
        "ok": True,
        "passed": passed,
        "summary": summary,
        "concerns": concerns,
        "flags": flags,
        "source": {
            "path": str(src_p),
            "sha256": src_info["sha256"],
            "width": src_w,
            "height": src_h,
            "aspect_ratio": src_ratio,
            "aspect_label": src_aspect_info.get("standard_label"),
            "format": src_info.get("format"),
            "mode": src_info.get("mode"),
            "has_icc_profile": src_info.get("has_icc_profile"),
        },
        "output": {
            "path": str(out_p),
            "sha256": out_info["sha256"],
            "width": out_w,
            "height": out_h,
            "aspect_ratio": out_ratio,
            "aspect_label": out_aspect_info.get("standard_label"),
            "format": out_info.get("format"),
            "mode": out_info.get("mode"),
            "has_icc_profile": out_info.get("has_icc_profile"),
        },
        "previews": {
            "source_preview_path": str(src_preview_file),
            "output_preview_path": str(out_preview_file),
            "source_preview_dimensions": list(src_prev_dim),
            "output_preview_dimensions": list(out_prev_dim),
        },
        "crops": crops_data,
        "mechanical_checks": mechanical_checks,
        "retry_tracking": retry_tracking,
    }
