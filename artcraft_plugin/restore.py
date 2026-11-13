"""Restoration recipes, checkpointing, and before/after visual inspection tooling."""

from __future__ import annotations

import datetime
import json
import math
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter

from .discovery import find_cli_binary
from .runner import run_artcraft_cli, spot_heal
from .verify import _count_changed_pixels, _validate_region, inspect_image, sha256_file


SUPPORTED_RECIPES = (
    "faded_tones",
    "color_cast",
    "dust_and_scratches",
    "noise_and_grain",
    "sharpening",
    "enlargement",
)

UNSUPPORTED_OPERATIONS = (
    "reconstruct_missing_face",
    "reconstruct_missing_lettering",
    "reconstruct_missing_content",
    "generative_inpainting_hallucination",
    "destructive_in_place_overwrite",
    "excessive_halo_sharpening",
    "extreme_chroma_shift",
)

RECONSTRUCTION_KEYWORDS = (
    "missing_face",
    "missing_lettering",
    "missing_text",
    "missing_content",
    "reconstruct_face",
    "reconstruct_lettering",
    "reconstruct_text",
    "inpaint_face",
    "inpaint_text",
    "hallucinate_detail",
)


# Safe parameter bounds to prevent quality destruction or halo artifacts
SAFE_BOUNDS: Dict[str, Dict[str, Any]] = {
    "faded_tones": {
        "in_black_max": 50,      # Avoid crushing shadow detail (> 50 is destructive)
        "in_white_min": 200,     # Avoid blowing highlights (< 200 is destructive)
        "gamma_min": 0.7,
        "gamma_max": 1.5,
        "contrast_max": 40,
    },
    "color_cast": {
        "shift_max": 45,         # Midtone shifts > 45 severely discolor skin tones
    },
    "noise_and_grain": {
        "strength_max": 8,       # Max noise reduction strength (0-10)
        "preserve_details_min": 35,  # Preserves facial details and lettering
    },
    "sharpening": {
        "amount_max": 120,       # Amounts > 120 create harsh halos/fringing
        "radius_max": 2.2,       # Large radii create broad cartoonish contours
    },
    "enlargement": {
        "scale_max": 4.0,        # Factor > 4x without AI hallucination loses photographic fidelity
    },
}


class RestorationError(Exception):
    """Base exception for restoration failures."""


class GateDecisionRequired(RestorationError):
    """Raised when an operation encounters the Stop/Ask gate."""


def check_stop_ask_gate(
    recipe: str,
    parameters: Optional[Dict[str, Any]] = None,
    *,
    reconstruct_missing: bool = False,
    content_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluate whether the request must stop and ask for human operator decision.

    Stops when:
    1. Reconstructing missing faces, lettering, or important content is requested.
    2. Generative inpainting or content hallucination is specified.
    3. Parameters exceed safe non-destructive restoration boundaries.
    """
    params = parameters or {}

    # Check explicit reconstruction flags
    if reconstruct_missing:
        return {
            "status": "needs_decision",
            "reason": (
                "Request involves reconstructing missing photographic content. "
                "Safe restoration preserves existing photographic material but does "
                "not invent or hallucinate missing features without operator decision."
            ),
            "gate_category": "missing_content_reconstruction",
        }

    # Check content type indicators
    if content_type:
        norm_type = content_type.strip().lower()
        if any(kw in norm_type for kw in ("face", "lettering", "text", "missing", "identity")):
            return {
                "status": "needs_decision",
                "reason": (
                    f"Target content type '{content_type}' involves potential reconstruction of "
                    "missing facial identity, lettering, or key features. Operator decision required."
                ),
                "gate_category": "missing_content_reconstruction",
            }

    # Check parameter keys and strings for reconstruction requests
    for key, val in params.items():
        key_str = str(key).lower()
        val_str = str(val).lower() if isinstance(val, (str, bool)) else ""
        if any(kw in key_str or kw in val_str for kw in RECONSTRUCTION_KEYWORDS):
            return {
                "status": "needs_decision",
                "reason": (
                    f"Parameter '{key}' specifies reconstruction of missing facial details or text. "
                    "Operator decision required before altering photographic truth."
                ),
                "gate_category": "missing_content_reconstruction",
            }

    # Check parameter bounds per recipe
    if recipe == "faded_tones":
        in_black = params.get("in_black", params.get("inBlack", 0))
        in_white = params.get("in_white", params.get("inWhite", 255))
        contrast = params.get("contrast", 0)
        gamma = params.get("gamma", 1.0)
        if in_black > SAFE_BOUNDS["faded_tones"]["in_black_max"]:
            return {
                "status": "needs_decision",
                "reason": f"Requested in_black={in_black} exceeds safe limit ({SAFE_BOUNDS['faded_tones']['in_black_max']}), which would crush deep shadow detail.",
                "gate_category": "unsafe_parameters",
            }
        if in_white < SAFE_BOUNDS["faded_tones"]["in_white_min"]:
            return {
                "status": "needs_decision",
                "reason": f"Requested in_white={in_white} is below safe limit ({SAFE_BOUNDS['faded_tones']['in_white_min']}), which would blow out delicate highlight detail.",
                "gate_category": "unsafe_parameters",
            }
        if contrast > SAFE_BOUNDS["faded_tones"]["contrast_max"]:
            return {
                "status": "needs_decision",
                "reason": f"Contrast boost={contrast} exceeds safe limit ({SAFE_BOUNDS['faded_tones']['contrast_max']}).",
                "gate_category": "unsafe_parameters",
            }

    elif recipe == "color_cast":
        shift_max = SAFE_BOUNDS["color_cast"]["shift_max"]
        midtones = params.get("midtones")
        if isinstance(midtones, (list, tuple)):
            if any(abs(v) > shift_max for v in midtones if isinstance(v, (int, float))):
                return {
                    "status": "needs_decision",
                    "reason": f"Color balance shift in midtones {midtones} exceeds safe limit (+/-{shift_max}), risking unnatural skin tones and artifacting.",
                    "gate_category": "unsafe_parameters",
                }

    elif recipe == "noise_and_grain":
        strength = params.get("strength", 4)
        preserve_details = params.get("preserve_details", params.get("preserveDetails", 70))
        if strength > SAFE_BOUNDS["noise_and_grain"]["strength_max"] and preserve_details < SAFE_BOUNDS["noise_and_grain"]["preserve_details_min"]:
            return {
                "status": "needs_decision",
                "reason": f"Extreme noise reduction (strength={strength}, preserveDetails={preserve_details}) causes plastic skin texture and obliterates lettering.",
                "gate_category": "unsafe_parameters",
            }

    elif recipe == "sharpening":
        amount = params.get("amount", 50)
        radius = params.get("radius", 1.0)
        if amount > SAFE_BOUNDS["sharpening"]["amount_max"]:
            return {
                "status": "needs_decision",
                "reason": f"Sharpening amount={amount} exceeds safe limit ({SAFE_BOUNDS['sharpening']['amount_max']}), producing distracting edge halos.",
                "gate_category": "unsafe_parameters",
            }
        if radius > SAFE_BOUNDS["sharpening"]["radius_max"]:
            return {
                "status": "needs_decision",
                "reason": f"Sharpening radius={radius} exceeds safe limit ({SAFE_BOUNDS['sharpening']['radius_max']}), causing thick border artifacts.",
                "gate_category": "unsafe_parameters",
            }

    elif recipe == "enlargement":
        scale = params.get("scale")
        if scale is not None and float(scale) > SAFE_BOUNDS["enlargement"]["scale_max"]:
            return {
                "status": "needs_decision",
                "reason": f"Enlargement scale={scale} exceeds safe limit ({SAFE_BOUNDS['enlargement']['scale_max']}x). Extreme scaling requires operator review.",
                "gate_category": "unsafe_parameters",
            }

    return None


def generate_before_after_crops(
    before_path: Union[str, Path],
    after_path: Union[str, Path],
    output_dir: Union[str, Path],
    *,
    recipe_name: str = "Restoration",
    regions: Optional[Sequence[Sequence[int]]] = None,
    crop_size: int = 256,
    target_print_ppi: int = 300,
) -> List[Dict[str, Any]]:
    """Produce matching native-resolution (1:1) and print-scale crops and comparisons.

    Returns a list of crop comparison dictionaries with file paths.
    """
    out_dir = Path(output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(before_path) as im_before_raw, Image.open(after_path) as im_after_raw:
        im_before = im_before_raw.convert("RGB")
        im_after = im_after_raw.convert("RGB")

    bw, bh = im_before.size
    aw, ah = im_after.size
    scale_factor = aw / bw if bw > 0 else 1.0

    # Determine crop boxes
    crop_boxes: List[Tuple[int, int, int, int]] = []
    if regions:
        for r in regions:
            if len(r) == 4:
                x, y, w, h = (int(v) for v in r)
                # Ensure within before image
                x0 = max(0, min(bw - 1, x))
                y0 = max(0, min(bh - 1, y))
                x1 = max(x0 + 1, min(bw, x0 + w))
                y1 = max(y0 + 1, min(bh, y0 + h))
                crop_boxes.append((x0, y0, x1, y1))
    else:
        # Default representative crops:
        # 1. Center crop
        cx, cy = bw // 2, bh // 2
        half = min(crop_size // 2, bw // 2, bh // 2)
        if half > 0:
            crop_boxes.append((cx - half, cy - half, cx + half, cy + half))

        # 2. Detail patch
        c_sz = min(crop_size, bw // 2, bh // 2)
        px, py = max(0, bw // 6), max(0, bh // 6)
        if c_sz > 0 and px + c_sz <= bw and py + c_sz <= bh:
            crop_boxes.append((px, py, px + c_sz, py + c_sz))

    if not crop_boxes:
        crop_boxes.append((0, 0, min(bw, crop_size), min(bh, crop_size)))

    crop_results: List[Dict[str, Any]] = []

    for idx, (x0, y0, x1, y1) in enumerate(crop_boxes):
        prefix = f"crop_{idx + 1:02d}"

        # 1. Native-resolution crop
        before_crop = im_before.crop((x0, y0, x1, y1))

        # Matching area in after image (scaled if image was resized/enlarged)
        ax0 = int(round(x0 * scale_factor))
        ay0 = int(round(y0 * scale_factor))
        ax1 = int(round(x1 * scale_factor))
        ay1 = int(round(y1 * scale_factor))
        ax1 = min(aw, max(ax0 + 1, ax1))
        ay1 = min(ah, max(ay0 + 1, ay1))
        after_crop = im_after.crop((ax0, ay0, ax1, ay1))

        # Save individual native crops
        native_before_path = out_dir / f"{prefix}_native_before.png"
        native_after_path = out_dir / f"{prefix}_native_after.png"
        before_crop.save(native_before_path, format="PNG")
        after_crop.save(native_after_path, format="PNG")

        # Create side-by-side native comparison canvas
        # If sizes differ due to enlargement, resize before crop visually for side-by-side or match heights
        norm_h = max(before_crop.height, after_crop.height, 120)
        nb_w = int(round(before_crop.width * (norm_h / before_crop.height)))
        na_w = int(round(after_crop.width * (norm_h / after_crop.height)))
        nb_disp = before_crop.resize((nb_w, norm_h), Image.Resampling.NEAREST if scale_factor == 1.0 else Image.Resampling.BILINEAR)
        na_disp = after_crop.resize((na_w, norm_h), Image.Resampling.BILINEAR)

        native_strip_w = nb_disp.width + na_disp.width + 12
        native_strip_h = norm_h + 36
        native_comp = Image.new("RGB", (native_strip_w, native_strip_h), (30, 32, 38))
        draw_native = ImageDraw.Draw(native_comp)
        draw_native.text((8, 10), "BEFORE (1:1 Native)", fill=(210, 215, 225))
        draw_native.text((nb_disp.width + 16, 10), f"AFTER ({recipe_name})", fill=(100, 220, 140))
        native_comp.paste(nb_disp, (0, 36))
        native_comp.paste(na_disp, (nb_disp.width + 12, 36))
        native_strip_path = out_dir / f"{prefix}_native_comparison.png"
        native_comp.save(native_strip_path, format="PNG")

        # 2. Print-scale crop (simulated appearance at intended physical print PPI)
        # At print PPI (e.g. 300), a 1-inch area is target_print_ppi x target_print_ppi pixels.
        # Both crops are shown at the target print viewing scale.
        print_box_size = min(target_print_ppi, before_crop.width, after_crop.width)
        if print_box_size > 0:
            pb_before = before_crop.resize((print_box_size, print_box_size), Image.Resampling.LANCZOS)
            pb_after = after_crop.resize((print_box_size, print_box_size), Image.Resampling.LANCZOS)
        else:
            pb_before = before_crop
            pb_after = after_crop

        print_before_path = out_dir / f"{prefix}_printscale_before.png"
        print_after_path = out_dir / f"{prefix}_printscale_after.png"
        pb_before.save(print_before_path, format="PNG")
        pb_after.save(print_after_path, format="PNG")

        print_strip_w = pb_before.width + pb_after.width + 12
        print_strip_h = pb_before.height + 36
        print_comp = Image.new("RGB", (print_strip_w, print_strip_h), (30, 32, 38))
        draw_print = ImageDraw.Draw(print_comp)
        draw_print.text((8, 10), f"BEFORE (Print Scale @ {target_print_ppi} PPI)", fill=(210, 215, 225))
        draw_print.text((pb_before.width + 16, 10), f"AFTER ({recipe_name})", fill=(100, 220, 140))
        print_comp.paste(pb_before, (0, 36))
        print_comp.paste(pb_after, (pb_before.width + 12, 36))
        print_strip_path = out_dir / f"{prefix}_printscale_comparison.png"
        print_comp.save(print_strip_path, format="PNG")

        crop_results.append({
            "index": idx + 1,
            "region_before": [x0, y0, x1 - x0, y1 - y0],
            "region_after": [ax0, ay0, ax1 - ax0, ay1 - ay0],
            "native": {
                "before_path": str(native_before_path),
                "after_path": str(native_after_path),
                "comparison_strip_path": str(native_strip_path),
                "dimensions": [before_crop.width, before_crop.height],
            },
            "print_scale": {
                "before_path": str(print_before_path),
                "after_path": str(print_after_path),
                "comparison_strip_path": str(print_strip_path),
                "ppi": target_print_ppi,
            },
        })

    return crop_results


def _record_checkpoint(
    checkpoint_dir: Path,
    step_index: int,
    step_name: str,
    recipe: str,
    input_path: str,
    output_path: str,
    parameters: Dict[str, Any],
    crops: List[Dict[str, Any]],
    diff_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Save step metadata and update manifest.json in the checkpoint directory."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = checkpoint_dir / "manifest.json"

    history: List[Dict[str, Any]] = []
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    checkpoint_record = {
        "step_index": step_index,
        "step_name": step_name,
        "recipe": recipe,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_path": str(Path(input_path).resolve()),
        "output_path": str(Path(output_path).resolve()),
        "input_sha256": sha256_file(input_path),
        "output_sha256": sha256_file(output_path),
        "parameters": parameters,
        "changed_pixels": diff_info.get("changed_pixels"),
        "total_pixels": diff_info.get("total_pixels"),
        "changed_ratio": diff_info.get("changed_ratio"),
        "crops": crops,
    }

    # Write step-specific JSON
    step_file = checkpoint_dir / f"{step_name}.json"
    with step_file.open("w", encoding="utf-8") as f:
        json.dump(checkpoint_record, f, indent=2)

    # Update manifest
    history.append(checkpoint_record)
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    return checkpoint_record


def list_checkpoints(checkpoint_dir: Union[str, Path]) -> List[Dict[str, Any]]:
    """List all checkpoints in a restoration checkpoint directory."""
    cdir = Path(checkpoint_dir).expanduser()
    manifest_path = cdir / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_checkpoint(checkpoint_dir: Union[str, Path], step_identifier: Union[int, str]) -> Optional[Dict[str, Any]]:
    """Get a specific checkpoint by index (1-based) or step name."""
    items = list_checkpoints(checkpoint_dir)
    for it in items:
        if it.get("step_index") == step_identifier or it.get("step_name") == str(step_identifier):
            return it
    return None


# =============================================================================
# RECIPE IMPLEMENTATIONS
# =============================================================================

def apply_faded_tones(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    parameters: Optional[Dict[str, Any]] = None,
    *,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Gentle tonal correction preserving highlight and shadow detail.

    Uses PhotoCraft's `image.adjustments.levels` with safe boundary guards.
    """
    params = parameters or {}
    in_black = int(params.get("in_black", params.get("inBlack", 12)))
    in_white = int(params.get("in_white", params.get("inWhite", 242)))
    gamma = float(params.get("gamma", 1.05))

    cli_params = {
        "inBlack": in_black,
        "inWhite": in_white,
        "gamma": gamma,
        "outBlack": int(params.get("outBlack", 0)),
        "outWhite": int(params.get("outWhite", 255)),
    }

    result = run_artcraft_cli(
        "photocraft",
        ["run", str(input_path), "--cmd", "image.adjustments.levels", "--params", json.dumps(cli_params), "--out", str(output_path)],
        input_path=str(input_path),
        output_path=str(output_path),
        timeout_s=timeout_s,
    )
    return result


def apply_color_cast(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    parameters: Optional[Dict[str, Any]] = None,
    *,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Neutral-balance and color adjustment preserving believable skin tones and warmth.

    Uses PhotoCraft's `image.adjustments.colorBalance` with preserveLuminosity=True.
    """
    params = parameters or {}
    # midtones is [cyan-red, magenta-green, yellow-blue] in -100..100
    midtones = params.get("midtones", [0, 0, 15])
    shadows = params.get("shadows", [0, 0, 0])
    highlights = params.get("highlights", [0, 0, 0])
    preserve_luminosity = bool(params.get("preserveLuminosity", True))

    cli_params = {
        "midtones": list(midtones),
        "shadows": list(shadows),
        "highlights": list(highlights),
        "preserveLuminosity": preserve_luminosity,
    }

    result = run_artcraft_cli(
        "photocraft",
        ["run", str(input_path), "--cmd", "image.adjustments.colorBalance", "--params", json.dumps(cli_params), "--out", str(output_path)],
        input_path=str(input_path),
        output_path=str(output_path),
        timeout_s=timeout_s,
    )
    return result


def apply_dust_and_scratches(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    parameters: Optional[Dict[str, Any]] = None,
    *,
    region: Optional[Sequence[int]] = None,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Localized healing of dust speckles and scratches preserving nearby edges.

    If points are provided, uses localized `paint.spotHealing` brush.
    Otherwise uses `filter.noise.dustAndScratches` with gentle radius and threshold.
    """
    params = parameters or {}
    points = params.get("points")
    size = params.get("size", 12)

    # Localized spot healing brush when points/region are provided
    if points and region:
        return spot_heal(
            str(input_path),
            str(output_path),
            points=list(points),
            size=int(size),
            region=list(region),
            timeout_s=timeout_s,
        )

    # Filter-based dust & scratches reduction
    radius = int(params.get("radius", 1))
    threshold = int(params.get("threshold", 15))
    cli_params = {"radius": radius, "threshold": threshold}

    result = run_artcraft_cli(
        "photocraft",
        ["run", str(input_path), "--cmd", "filter.noise.dustAndScratches", "--params", json.dumps(cli_params), "--out", str(output_path)],
        input_path=str(input_path),
        output_path=str(output_path),
        timeout_s=timeout_s,
    )
    return result


def apply_noise_and_grain(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    parameters: Optional[Dict[str, Any]] = None,
    *,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Selective noise reduction retaining facial detail, lettering, and texture.

    Uses PhotoCraft's `filter.noise.reduceNoise`.
    """
    params = parameters or {}
    strength = float(params.get("strength", 4))
    preserve_details = float(params.get("preserve_details", params.get("preserveDetails", 70)))
    reduce_color_noise = float(params.get("reduce_color_noise", params.get("reduceColorNoise", 45)))
    sharpen_details = float(params.get("sharpen_details", params.get("sharpenDetails", 15)))
    remove_jpeg_artifact = bool(params.get("removeJpegArtifact", False))

    cli_params = {
        "strength": strength,
        "preserveDetails": preserve_details,
        "reduceColorNoise": reduce_color_noise,
        "sharpenDetails": sharpen_details,
        "removeJpegArtifact": remove_jpeg_artifact,
    }

    result = run_artcraft_cli(
        "photocraft",
        ["run", str(input_path), "--cmd", "filter.noise.reduceNoise", "--params", json.dumps(cli_params), "--out", str(output_path)],
        input_path=str(input_path),
        output_path=str(output_path),
        timeout_s=timeout_s,
    )
    return result


def apply_sharpening(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    parameters: Optional[Dict[str, Any]] = None,
    *,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Restrained sharpening avoiding distracting halos and artifacts.

    Uses PhotoCraft's `filter.sharpen.unsharpMask` with safe amount, radius, and threshold.
    """
    params = parameters or {}
    amount = float(params.get("amount", 50))
    radius = float(params.get("radius", 1.0))
    threshold = float(params.get("threshold", 2))

    cli_params = {
        "amount": amount,
        "radius": radius,
        "threshold": threshold,
    }

    result = run_artcraft_cli(
        "photocraft",
        ["run", str(input_path), "--cmd", "filter.sharpen.unsharpMask", "--params", json.dumps(cli_params), "--out", str(output_path)],
        input_path=str(input_path),
        output_path=str(output_path),
        timeout_s=timeout_s,
    )
    return result


def apply_enlargement(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    parameters: Optional[Dict[str, Any]] = None,
    *,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Proportional enlargement + restrained output sharpening preserving composition.

    Chains PhotoCraft's `image.imageSize` (resample=preserveDetails) and `filter.sharpen.unsharpMask`.
    """
    params = parameters or {}
    info = inspect_image(str(input_path))
    if not info.get("valid"):
        raise ValueError("input_path must be a valid image")

    orig_w = info["width"]
    orig_h = info["height"]

    scale = params.get("scale")
    target_w = params.get("width")
    target_h = params.get("height")

    if scale is not None:
        target_w = int(round(orig_w * float(scale)))
        target_h = int(round(orig_h * float(scale)))
    elif target_w is not None and target_h is None:
        target_h = int(round(orig_h * (target_w / orig_w)))
    elif target_h is not None and target_w is None:
        target_w = int(round(orig_w * (target_h / orig_h)))
    elif target_w is None and target_h is None:
        # Default 1.5x upscaling if not specified
        target_w = int(round(orig_w * 1.5))
        target_h = int(round(orig_h * 1.5))

    resample = params.get("resample", "preserveDetails")
    sharpen_amount = float(params.get("sharpen_amount", 40))
    sharpen_radius = float(params.get("sharpen_radius", 0.8))

    size_params = {"width": target_w, "height": target_h, "resample": resample}
    usm_params = {"amount": sharpen_amount, "radius": sharpen_radius, "threshold": 1}

    result = run_artcraft_cli(
        "photocraft",
        [
            "run", str(input_path),
            "--cmd", "image.imageSize", "--params", json.dumps(size_params),
            "--cmd", "filter.sharpen.unsharpMask", "--params", json.dumps(usm_params),
            "--out", str(output_path),
        ],
        input_path=str(input_path),
        output_path=str(output_path),
        expected_width=target_w,
        expected_height=target_h,
        timeout_s=timeout_s,
    )
    return result


# =============================================================================
# RESTORATION STEP ORCHESTRATION & GATE
# =============================================================================

def restore_step(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    recipe: str,
    parameters: Optional[Dict[str, Any]] = None,
    *,
    region: Optional[Sequence[int]] = None,
    checkpoint_dir: Optional[Union[str, Path]] = None,
    step_name: Optional[str] = None,
    crop_regions: Optional[Sequence[Sequence[int]]] = None,
    target_print_ppi: int = 300,
    reconstruct_missing: bool = False,
    content_type: Optional[str] = None,
    allow_overwrite: bool = False,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Execute a single verified restoration step with checkpointing and crop comparisons.

    Enforces the Stop/Ask Gate for missing face/lettering/content reconstruction
    and unsafe parameter bounds.
    """
    in_path = Path(input_path).expanduser().resolve()
    out_path = Path(output_path).expanduser().absolute()
    params = parameters or {}

    # Check input file existence and validity
    if not in_path.is_file():
        return {
            "ok": False,
            "status": "error",
            "error": f"input_path does not exist: {input_path}",
        }

    in_info = inspect_image(str(in_path))
    if not in_info.get("valid"):
        return {
            "ok": False,
            "status": "error",
            "error": f"input_path is not a readable image: {in_info.get('error')}",
        }

    # Non-destructive safety checks
    if in_path == out_path:
        return {
            "ok": False,
            "status": "error",
            "error": "output_path must be distinct from input_path to preserve source",
        }

    if out_path.exists() and not allow_overwrite:
        return {
            "ok": False,
            "status": "error",
            "error": f"output_path already exists and allow_overwrite is False: {output_path}",
        }

    norm_recipe = recipe.strip().lower()
    if norm_recipe not in SUPPORTED_RECIPES:
        return {
            "ok": False,
            "status": "error",
            "error": f"Unsupported recipe '{recipe}'. Supported: {list(SUPPORTED_RECIPES)}",
            "unsupported_operations": list(UNSUPPORTED_OPERATIONS),
        }

    # 1. EVALUATE STOP / ASK GATE BEFORE ANY WORK
    gate_decision = check_stop_ask_gate(
        norm_recipe,
        params,
        reconstruct_missing=reconstruct_missing,
        content_type=content_type,
    )
    if gate_decision is not None:
        # Crucial: DO NOT MUTATE SOURCE OR WRITE OUTPUT FILE
        return {
            "ok": False,
            "status": "needs_decision",
            "recipe": norm_recipe,
            "reason": gate_decision["reason"],
            "gate_category": gate_decision.get("gate_category"),
            "original_intact": True,
            "source_sha256": in_info["sha256"],
            "input_path": str(in_path),
            "output_path": None,
            "checkpoint": None,
        }

    # Setup checkpoint paths
    cdir = Path(checkpoint_dir).expanduser() if checkpoint_dir else out_path.parent / "checkpoints"
    cdir.mkdir(parents=True, exist_ok=True)

    manifest = list_checkpoints(cdir)
    step_idx = len(manifest) + 1
    s_name = step_name or f"step_{step_idx:03d}_{norm_recipe}"
    crops_dir = cdir / f"{s_name}_crops"

    # 2. DISPATCH RECIPE EXECUTION
    try:
        if norm_recipe == "faded_tones":
            exec_res = apply_faded_tones(in_path, out_path, params, timeout_s=timeout_s)
        elif norm_recipe == "color_cast":
            exec_res = apply_color_cast(in_path, out_path, params, timeout_s=timeout_s)
        elif norm_recipe == "dust_and_scratches":
            exec_res = apply_dust_and_scratches(in_path, out_path, params, region=region, timeout_s=timeout_s)
        elif norm_recipe == "noise_and_grain":
            exec_res = apply_noise_and_grain(in_path, out_path, params, timeout_s=timeout_s)
        elif norm_recipe == "sharpening":
            exec_res = apply_sharpening(in_path, out_path, params, timeout_s=timeout_s)
        elif norm_recipe == "enlargement":
            exec_res = apply_enlargement(in_path, out_path, params, timeout_s=timeout_s)
        else:
            raise ValueError(f"Unknown recipe {norm_recipe}")
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "error": f"Recipe execution failed: {exc}",
        }

    if not exec_res.get("ok"):
        return {
            "ok": False,
            "status": "error",
            "error": exec_res.get("error", "CLI execution returned failure"),
            "stderr": exec_res.get("stderr"),
        }

    # Verify output file
    out_info = inspect_image(str(out_path))
    if not out_info.get("valid"):
        return {
            "ok": False,
            "status": "error",
            "error": f"Generated output is not a valid image: {out_info.get('error')}",
        }

    # Verify source was untouched
    if sha256_file(in_path) != in_info["sha256"]:
        raise ValueError("Source file was modified during restoration step!")

    # Calculate diff stats
    diff_info: Dict[str, Any] = {}
    if in_info["width"] == out_info["width"] and in_info["height"] == out_info["height"]:
        with Image.open(in_path) as im1, Image.open(out_path) as im2:
            changed = _count_changed_pixels(im1, im2)
            total = im1.width * im1.height
            diff_info = {
                "changed_pixels": changed,
                "total_pixels": total,
                "changed_ratio": round(changed / total, 6) if total else 0.0,
            }
    else:
        diff_info = {
            "changed_pixels": out_info["width"] * out_info["height"],
            "total_pixels": out_info["width"] * out_info["height"],
            "dimensions_changed": [
                [in_info["width"], in_info["height"]],
                [out_info["width"], out_info["height"]],
            ],
        }

    # 3. GENERATE NATIVE AND PRINT-SCALE CROPS FOR VISUAL INSPECTION
    effective_regions = list(crop_regions) if crop_regions else []
    if region and not effective_regions:
        effective_regions.append(list(region))

    crops = generate_before_after_crops(
        in_path,
        out_path,
        crops_dir,
        recipe_name=norm_recipe.replace("_", " ").title(),
        regions=effective_regions if effective_regions else None,
        target_print_ppi=target_print_ppi,
    )

    # 4. SAVE CHECKPOINT RECORD
    checkpoint_record = _record_checkpoint(
        cdir,
        step_index=step_idx,
        step_name=s_name,
        recipe=norm_recipe,
        input_path=str(in_path),
        output_path=str(out_path),
        parameters=params,
        crops=crops,
        diff_info=diff_info,
    )

    return {
        "ok": True,
        "status": "applied",
        "recipe": norm_recipe,
        "step_name": s_name,
        "step_index": step_idx,
        "input_path": str(in_path),
        "output_path": str(out_path),
        "source_sha256": in_info["sha256"],
        "output_sha256": out_info["sha256"],
        "diff": diff_info,
        "checkpoint": checkpoint_record,
        "crops": crops,
    }
