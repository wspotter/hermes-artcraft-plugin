"""Photograph inspection helpers for ArtCraft plugin.

Generates whole-photo previews, native-resolution crops, orientation and
color-profile metadata, effective print PPI calculations, and measured clues
(endpoint clipping, sharpness, noise) with explicit measurement limits.
"""

from __future__ import annotations

import io
import math
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageCms, ImageFilter, ImageStat

try:
    import numpy as np
except ImportError:
    np = None

from .verify import sha256_file


MEASUREMENT_LIMITS: List[str] = [
    (
        "Endpoint clipping measurements cannot distinguish intentional specular highlights "
        "(catchlights, bright light sources, clean white backdrops, snow) from "
        "unintentionally blown-out highlights with lost detail."
    ),
    (
        "Shadow clipping measurements cannot distinguish intentional deep blacks "
        "(silhouettes, high-contrast chiaroscuro, dark backgrounds, borders) from "
        "unintentionally crushed shadow detail."
    ),
    (
        "Sharpness (Laplacian variance) is scene-dependent; intentional shallow depth of field, "
        "soft portrait backgrounds (bokeh), or foggy scenes naturally exhibit low variance "
        "without being defective."
    ),
    (
        "Noise estimation measures high-frequency variance in smooth regions but cannot "
        "distinguish authentic, desirable film grain from digital sensor noise or "
        "compression artifacts."
    ),
    (
        "Physical localized defects (scratches, dust specks, folds, chemical stains, tears) "
        "cannot be detected by global summary metrics alone; they require visual examination "
        "of native-resolution crops."
    ),
]


def determine_orientation(width: int, height: int) -> str:
    """Return 'landscape', 'portrait', or 'square'."""
    if width > height:
        return "landscape"
    elif height > width:
        return "portrait"
    return "square"


def determine_aspect_ratio(width: int, height: int) -> Dict[str, Any]:
    """Calculate numerical aspect ratio and nearest standard ratio label."""
    if height == 0:
        return {"ratio": 0.0, "standard_label": "invalid"}
    ratio = round(width / height, 4)
    # Check common photography ratios
    standards = [
        (1.0, "1:1"),
        (4 / 3, "4:3"),
        (3 / 4, "3:4"),
        (3 / 2, "3:2"),
        (2 / 3, "2:3"),
        (5 / 4, "5:4"),
        (4 / 5, "4:5"),
        (16 / 9, "16:9"),
        (9 / 16, "9:16"),
        (14 / 11, "14:11"),
        (11 / 14, "11:14"),
        (7 / 5, "7:5"),
        (5 / 7, "5:7"),
    ]
    matched_label = None
    for target_ratio, label in standards:
        if abs(ratio - target_ratio) < 0.025:
            matched_label = label
            break

    gcd_val = math.gcd(width, height)
    simplified = f"{width // gcd_val}:{height // gcd_val}" if gcd_val else f"{width}:{height}"

    return {
        "ratio_float": ratio,
        "standard_label": matched_label,
        "simplified_ratio": simplified,
    }


def extract_color_profile(img: Image.Image) -> Dict[str, Any]:
    """Extract embedded ICC profile information and color mode."""
    icc_raw = img.info.get("icc_profile")
    if not icc_raw:
        return {
            "has_icc_profile": False,
            "icc_profile_name": None,
            "color_mode": img.mode,
            "description": "Uncalibrated / no embedded ICC profile (assumed standard sRGB)",
        }

    profile_name: Optional[str] = None
    try:
        prof = ImageCms.getOpenProfile(io.BytesIO(icc_raw))
        desc = ImageCms.getProfileDescription(prof)
        if desc:
            profile_name = desc.strip()
    except Exception as exc:
        profile_name = f"Present ({len(icc_raw)} bytes, unparsed: {exc})"

    return {
        "has_icc_profile": True,
        "icc_profile_name": profile_name or "Embedded ICC Profile",
        "icc_profile_bytes": len(icc_raw),
        "color_mode": img.mode,
        "description": f"Embedded profile: {profile_name}",
    }


def compute_effective_ppi(
    width: int,
    height: int,
    target_sizes: Optional[Sequence[Any]] = None,
    *,
    target_print_sizes: Optional[Sequence[Any]] = None,
) -> List[Dict[str, Any]]:
    """Compute effective PPI for standard and requested print sizes.

    Orients print dimensions to match photo orientation (long side to long side).
    Reports both fill_ppi (full bleed borderless, requires crop if aspect mismatches)
    and fit_ppi (letterboxed/pillarboxed within paper, preserving whole image).
    """
    effective_targets = target_sizes if target_sizes is not None else target_print_sizes
    if effective_targets is None:
        targets: List[Tuple[str, float, float]] = [
            ("8x10", 8.0, 10.0),
            ("11x14", 11.0, 14.0),
            ("5x7", 5.0, 7.0),
            ("4x6", 4.0, 6.0),
            ("16x20", 16.0, 20.0),
        ]
    else:
        targets = []
        for idx, item in enumerate(effective_targets):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                targets.append((f"custom_{item[0]}x{item[1]}", float(item[0]), float(item[1])))
            elif isinstance(item, dict):
                w = float(item.get("width_in", item.get("w", 8.0)))
                h = float(item.get("height_in", item.get("h", 10.0)))
                name = item.get("name", f"custom_{w}x{h}")
                targets.append((name, w, h))

    is_landscape = width >= height
    results = []

    for name, dim_a, dim_b in targets:
        # Orient target paper to match image orientation
        if is_landscape:
            target_w = max(dim_a, dim_b)
            target_h = min(dim_a, dim_b)
        else:
            target_w = min(dim_a, dim_b)
            target_h = max(dim_a, dim_b)

        ppi_w = width / target_w
        ppi_h = height / target_h

        # fill_ppi: image must cover whole sheet, limiting dimension determines ppi
        fill_ppi = round(min(ppi_w, ppi_h), 1)
        # fit_ppi: entire image fits inside sheet with margins
        fit_ppi = round(max(ppi_w, ppi_h), 1)

        aspect_target = round(target_w / target_h, 4)
        aspect_img = round(width / height, 4) if height else 0.0
        aspect_match = abs(aspect_target - aspect_img) < 0.01

        # Rating tier based on fill_ppi
        if fill_ppi >= 300.0:
            rating = "Optimal (300+ PPI - archival / fine-art print)"
        elif fill_ppi >= 240.0:
            rating = "Very Good (240-299 PPI - sharp commercial print)"
        elif fill_ppi >= 180.0:
            rating = "Good (180-239 PPI - standard photo print)"
        elif fill_ppi >= 150.0:
            rating = "Acceptable (150-179 PPI - normal viewing distance)"
        else:
            rating = "Low (<150 PPI - pixelation risk, enlargement advised)"

        results.append(
            {
                "target_name": name,
                "print_dimensions_in": [target_w, target_h],
                "fill_ppi": fill_ppi,
                "fit_ppi": fit_ppi,
                "aspect_ratio_match": aspect_match,
                "crop_needed_for_borderless": not aspect_match,
                "quality_tier": rating,
            }
        )

    return results


def compute_measured_clues(img: Image.Image) -> Dict[str, Any]:
    """Compute measured clues: endpoint clipping, dynamic range, sharpness, and noise.

    Always pairs numbers with explicit measurement limits noting what the
    measurements can and cannot establish.
    """
    width, height = img.width, img.height
    total_pixels = width * height
    if total_pixels == 0:
        return {
            "error": "Empty image (zero pixels)",
            "measurement_limits": MEASUREMENT_LIMITS,
        }

    # Convert to RGB for uniform channel analysis
    rgb = img.convert("RGB")

    if np is not None:
        arr = np.array(rgb)
        # Pure endpoint clipping (all channels simultaneously at limit)
        shadow_clipped_pixels = int(np.all(arr == 0, axis=-1).sum())
        highlight_clipped_pixels = int(np.all(arr == 255, axis=-1).sum())

        # Per-channel clipping
        r_chan = arr[..., 0]
        g_chan = arr[..., 1]
        b_chan = arr[..., 2]

        r_zero = int((r_chan == 0).sum())
        r_255 = int((r_chan == 255).sum())
        g_zero = int((g_chan == 0).sum())
        g_255 = int((g_chan == 255).sum())
        b_zero = int((b_chan == 0).sum())
        b_255 = int((b_chan == 255).sum())

        # Grayscale luminance using ITU-R 601-2 luma weights
        gray = r_chan.astype(float) * 0.299 + g_chan.astype(float) * 0.587 + b_chan.astype(float) * 0.114
        lum_min = float(np.min(gray))
        lum_max = float(np.max(gray))
        lum_mean = round(float(np.mean(gray)), 2)
        lum_std = round(float(np.std(gray)), 2)

        # Sharpness indicator: variance of the Laplacian
        if height >= 3 and width >= 3:
            lap = (
                gray[:-2, 1:-1]
                + gray[2:, 1:-1]
                + gray[1:-1, :-2]
                + gray[1:-1, 2:]
                - 4.0 * gray[1:-1, 1:-1]
            )
            sharpness_score = round(float(lap.var()), 2)
        else:
            sharpness_score = 0.0

        # Noise indicator: median standard deviation of smoothest 20% patches (16x16)
        # Excludes patches dominated by saturated endpoints (pure white/black clipping)
        patch_size = 16
        patch_stds: List[float] = []
        if height >= patch_size and width >= patch_size:
            for y in range(0, height - patch_size + 1, patch_size):
                for x in range(0, width - patch_size + 1, patch_size):
                    patch = gray[y : y + patch_size, x : x + patch_size]
                    # Skip patches dominated by hard clipping (> 50% pixels at 0 or 255)
                    clipped_in_patch = ((patch <= 0.5) | (patch >= 254.5)).mean()
                    if clipped_in_patch > 0.5:
                        continue
                    patch_stds.append(float(np.std(patch)))
        if patch_stds:
            patch_stds.sort()
            k = max(1, int(len(patch_stds) * 0.2))
            noise_std = round(float(np.median(patch_stds[:k])), 2)
        else:
            noise_std = 0.0

    else:
        # Pure-Pillow fallback
        stat = ImageStat.Stat(rgb)
        hist = rgb.histogram()
        r_hist = hist[0:256]
        g_hist = hist[256:512]
        b_hist = hist[512:768]

        r_zero = r_hist[0]
        r_255 = r_hist[255]
        g_zero = g_hist[0]
        g_255 = g_hist[255]
        b_zero = b_hist[0]
        b_255 = b_hist[255]

        # Use conservative estimate from L histogram for joint clipping
        l_img = rgb.convert("L")
        l_hist = l_img.histogram()
        shadow_clipped_pixels = l_hist[0]
        highlight_clipped_pixels = l_hist[255]

        l_stat = ImageStat.Stat(l_img)
        lum_min = float(l_stat.extrema[0][0])
        lum_max = float(l_stat.extrema[0][1])
        lum_mean = round(float(l_stat.mean[0]), 2)
        lum_std = round(float(l_stat.stddev[0]), 2)

        edges = l_img.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        sharpness_score = round(float(edge_stat.var[0]), 2)
        noise_std = round(float(lum_std * 0.1), 2)

    shadow_pct = round(shadow_clipped_pixels / total_pixels * 100, 3)
    highlight_pct = round(highlight_clipped_pixels / total_pixels * 100, 3)

    # Classifications for quick interpretation
    if sharpness_score >= 1000.0:
        sharpness_label = "High edge contrast / very sharp"
    elif sharpness_score >= 250.0:
        sharpness_label = "Moderate edge sharpness"
    elif sharpness_score >= 50.0:
        sharpness_label = "Gentle sharpness / soft details"
    else:
        sharpness_label = "Low edge contrast (soft focus, shallow DOF, or smooth content)"

    if noise_std <= 2.0:
        noise_label = "Clean / negligible noise"
    elif noise_std <= 6.0:
        noise_label = "Low noise / fine organic grain"
    elif noise_std <= 15.0:
        noise_label = "Moderate noise or noticeable grain"
    else:
        noise_label = "Heavy noise / pronounced sensor or scanning noise"

    return {
        "endpoint_clipping": {
            "shadow_clipped_percent": shadow_pct,
            "highlight_clipped_percent": highlight_pct,
            "shadow_clipped_pixels": shadow_clipped_pixels,
            "highlight_clipped_pixels": highlight_clipped_pixels,
            "per_channel_clipping": {
                "red": {
                    "zero_percent": round(r_zero / total_pixels * 100, 3),
                    "max_percent": round(r_255 / total_pixels * 100, 3),
                },
                "green": {
                    "zero_percent": round(g_zero / total_pixels * 100, 3),
                    "max_percent": round(g_255 / total_pixels * 100, 3),
                },
                "blue": {
                    "zero_percent": round(b_zero / total_pixels * 100, 3),
                    "max_percent": round(b_255 / total_pixels * 100, 3),
                },
            },
        },
        "dynamic_range": {
            "min_luminance": lum_min,
            "max_luminance": lum_max,
            "mean_luminance": lum_mean,
            "stddev_luminance": lum_std,
        },
        "sharpness": {
            "score": sharpness_score,
            "metric": "laplacian_variance",
            "interpretation": sharpness_label,
        },
        "noise": {
            "estimated_noise_std": noise_std,
            "metric": "smooth_patch_stddev",
            "interpretation": noise_label,
        },
        "measurement_limits": MEASUREMENT_LIMITS,
    }


def generate_preview(
    img: Image.Image,
    dest_path: Path,
    max_dimension: int = 1024,
) -> Dict[str, Any]:
    """Generate a whole-photo preview image bounded by max_dimension."""
    w, h = img.width, img.height
    if max(w, h) > max_dimension and max_dimension > 0:
        scale = max_dimension / max(w, h)
        pw = max(1, round(w * scale))
        ph = max(1, round(h * scale))
        preview = img.resize((pw, ph), Image.Resampling.LANCZOS)
    else:
        preview = img.copy()
        pw, ph = w, h
        scale = 1.0

    preview.save(dest_path, format="PNG")
    return {
        "path": str(dest_path),
        "width": pw,
        "height": ph,
        "scale_factor": round(pw / w, 4) if w else 1.0,
    }


def generate_native_crops(
    img: Image.Image,
    working_dir: Path,
    crop_size: int = 256,
    regions: Optional[Sequence[Sequence[int]]] = None,
) -> List[Dict[str, Any]]:
    """Extract native-resolution (1:1 pixel) crops from key regions.

    Crops center and 4 corners by default, plus any requested custom regions.
    """
    w, h = img.width, img.height
    cw = max(1, min(crop_size, w))
    ch = max(1, min(crop_size, h))

    crop_specs: List[Tuple[str, int, int, int, int]] = []

    if regions:
        for idx, reg in enumerate(regions):
            if len(reg) == 4:
                rx, ry, rw, rh = (int(v) for v in reg)
                # Clamp within image bounds
                rx = max(0, min(rx, max(0, w - 1)))
                ry = max(0, min(ry, max(0, h - 1)))
                rw = max(1, min(rw, w - rx))
                rh = max(1, min(rh, h - ry))
                crop_specs.append((f"region_{idx}", rx, ry, rw, rh))
    else:
        # Default strategic crops: center + 4 corners
        center_x = max(0, (w - cw) // 2)
        center_y = max(0, (h - ch) // 2)
        crop_specs.append(("center", center_x, center_y, cw, ch))

        # Corners
        crop_specs.append(("top_left", 0, 0, cw, ch))
        crop_specs.append(("top_right", max(0, w - cw), 0, cw, ch))
        crop_specs.append(("bottom_left", 0, max(0, h - ch), cw, ch))
        crop_specs.append(("bottom_right", max(0, w - cw), max(0, h - ch), cw, ch))

    results: List[Dict[str, Any]] = []
    # Deduplicate crops with identical boxes
    seen_boxes = set()

    for name, x, y, rw, rh in crop_specs:
        box_key = (x, y, rw, rh)
        if box_key in seen_boxes:
            continue
        seen_boxes.add(box_key)

        crop_box = (x, y, x + rw, y + rh)
        crop_img = img.crop(crop_box)
        crop_filename = f"crop_{name}_{rw}x{rh}_x{x}_y{y}.png"
        crop_path = working_dir / crop_filename
        crop_img.save(crop_path, format="PNG")

        results.append(
            {
                "name": name,
                "box": [x, y, rw, rh],
                "path": str(crop_path),
                "width": rw,
                "height": rh,
            }
        )

    return results


def prepare_inspection(
    path_str: str,
    *,
    working_dir: Optional[str | Path] = None,
    max_preview_dimension: int = 1024,
    crop_size: int = 256,
    regions: Optional[Sequence[Sequence[int]]] = None,
    target_print_sizes: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Prepare an image for agent visual inspection.

    Generates a bounded preview and 1:1 native-resolution crops into working_dir
    without altering the source file. Reports metadata, orientation, ICC profile,
    effective print PPI, and measured clues (endpoint clipping, sharpness, noise).
    """
    source_path = Path(path_str).expanduser()
    if not source_path.is_file():
        return {
            "exists": False,
            "valid": False,
            "path": str(source_path),
            "error": f"Image file does not exist: {source_path}",
        }

    # Verify image integrity and measure source SHA-256
    original_sha256 = sha256_file(source_path)
    original_size = source_path.stat().st_size

    try:
        with Image.open(source_path) as img:
            img.verify()
    except Exception as exc:
        return {
            "exists": True,
            "valid": False,
            "path": str(source_path),
            "size_bytes": original_size,
            "sha256": original_sha256,
            "error": f"Corrupt or unreadable image file: {exc}",
        }

    # Resolve working directory
    if working_dir is None:
        work_path = Path(tempfile.mkdtemp(prefix="artcraft_inspection_"))
    else:
        work_path = Path(working_dir).expanduser()
        work_path.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(source_path) as img:
            img.load()
            w, h = img.width, img.height
            orientation = determine_orientation(w, h)
            aspect_info = determine_aspect_ratio(w, h)
            color_info = extract_color_profile(img)
            dpi = img.info.get("dpi")

            # Generate whole-photo preview
            preview_filename = f"preview_{source_path.stem}.png"
            preview_path = work_path / preview_filename
            preview_info = generate_preview(img, preview_path, max_preview_dimension)

            # Generate 1:1 native crops
            crops_info = generate_native_crops(img, work_path, crop_size=crop_size, regions=regions)

            # Compute effective print PPI
            print_ppi = compute_effective_ppi(w, h, target_print_sizes=target_print_sizes)

            # Compute measured clues (clipping, sharpness, noise) with explicit limits
            clues = compute_measured_clues(img)

        # Confirm source file was not modified
        post_sha256 = sha256_file(source_path)
        if post_sha256 != original_sha256:
            raise RuntimeError("Source image was modified during inspection preparation!")

        return {
            "exists": True,
            "valid": True,
            "source": {
                "path": str(source_path),
                "filename": source_path.name,
                "size_bytes": original_size,
                "sha256": original_sha256,
                "format": img.format,
                "color_mode": img.mode,
                "width": w,
                "height": h,
                "orientation": orientation,
                "aspect_ratio": aspect_info,
                "dpi": list(dpi) if isinstance(dpi, tuple) else dpi,
                "color_profile": color_info,
            },
            "inspection_artifacts": {
                "working_dir": str(work_path),
                "whole_photo_preview": preview_info,
                "native_resolution_crops": crops_info,
            },
            "print_resolution": print_ppi,
            "measured_clues": clues,
        }

    except Exception as exc:
        return {
            "exists": True,
            "valid": False,
            "path": str(source_path),
            "size_bytes": original_size,
            "sha256": original_sha256,
            "error": f"Failed during inspection preparation: {exc}",
        }
