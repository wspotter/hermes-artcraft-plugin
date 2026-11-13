"""Print preparation module for ArtCraft plugin.

Prepares agreed print requests into correctly sized, verified delivery files
at specified physical dimensions (width_in, height_in) and PPI. Strictly preserves
proportions, enforces a clarification gate when instructions conflict between
crop and margins, reports effective source resolution separately from export
resolution, preserves ICC color profiles, and verifies the written delivery file
by reopening and decoding it.
"""

from __future__ import annotations

import io
import math
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageCms, ImageColor

from .inspect import determine_aspect_ratio, determine_orientation, extract_color_profile
from .verify import sha256_file


def compute_print_target_dimensions(
    width_in: float,
    height_in: float,
    ppi: int,
    source_width: int,
    source_height: int,
    orientation: str = "auto",
) -> Tuple[float, float, int, int, str]:
    """Calculate target physical inches, pixel dimensions, and applied orientation.

    Returns:
        (target_w_in, target_h_in, target_w_px, target_h_px, applied_orientation)
    """
    if width_in <= 0 or height_in <= 0:
        raise ValueError(f"Print dimensions must be positive, got width={width_in}, height={height_in}")
    if ppi <= 0:
        raise ValueError(f"PPI must be positive, got ppi={ppi}")

    src_orient = determine_orientation(source_width, source_height)
    orient_req = orientation.lower()

    if orient_req == "auto":
        if src_orient == "portrait":
            target_w_in = min(width_in, height_in)
            target_h_in = max(width_in, height_in)
            applied_orient = "portrait"
        elif src_orient == "landscape":
            target_w_in = max(width_in, height_in)
            target_h_in = min(width_in, height_in)
            applied_orient = "landscape"
        else:  # square
            if width_in == height_in:
                target_w_in = width_in
                target_h_in = height_in
                applied_orient = "square"
            else:
                target_w_in = min(width_in, height_in)
                target_h_in = max(width_in, height_in)
                applied_orient = "portrait"
    elif orient_req == "portrait":
        target_w_in = min(width_in, height_in)
        target_h_in = max(width_in, height_in)
        applied_orient = "portrait"
    elif orient_req == "landscape":
        target_w_in = max(width_in, height_in)
        target_h_in = min(width_in, height_in)
        applied_orient = "landscape"
    else:
        raise ValueError(
            f"Unsupported orientation '{orientation}'. Expected 'auto', 'portrait', or 'landscape'."
        )

    target_w_px = round(target_w_in * ppi)
    target_h_px = round(target_h_in * ppi)

    return target_w_in, target_h_in, target_w_px, target_h_px, applied_orient


def calculate_effective_source_ppi(
    source_width: int,
    source_height: int,
    target_width_in: float,
    target_height_in: float,
    fit_mode: str,
) -> float:
    """Calculate effective source PPI on the target printed sheet."""
    ppi_w = source_width / target_width_in
    ppi_h = source_height / target_height_in

    if fit_mode in ("margins", "fit"):
        # Image fits entirely inside sheet; scale is governed by the tighter fit
        return round(max(ppi_w, ppi_h), 1)
    else:
        # Borderless fill: image covers entire sheet; limiting dimension determines ppi
        return round(min(ppi_w, ppi_h), 1)


def parse_margin_color(color_spec: Union[str, Tuple[int, ...]]) -> Tuple[int, ...]:
    """Parse color string or tuple into an RGB/RGBA tuple."""
    if isinstance(color_spec, (tuple, list)):
        return tuple(int(c) for c in color_spec)
    if not isinstance(color_spec, str):
        return (255, 255, 255)

    color_lower = color_spec.lower().strip()
    if color_lower == "transparent":
        return (0, 0, 0, 0)
    try:
        return ImageColor.getrgb(color_spec)
    except Exception:
        return (255, 255, 255)


def prepare_print(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    width_in: float,
    height_in: float,
    *,
    orientation: str = "auto",
    fit_mode: str = "auto",
    confirm_crop: bool = False,
    ppi: int = 300,
    output_format: str = "auto",
    margin_color: Union[str, Tuple[int, ...]] = "white",
    preserve_master_path: Optional[Union[str, Path]] = None,
    allow_upscale: bool = False,
    target_icc: Optional[str] = None,
    preview_path: Optional[Union[str, Path]] = None,
    max_preview_dimension: int = 1024,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Prepare a verified print delivery file from source image.

    If instructions conflict (e.g. borderless fit requested on mismatched aspect ratios
    without confirm_crop=True), stops without writing the output file and returns
    `status: "needs_clarification"` with a parameterized clarification question.

    Returns:
        Dict reporting status, delivery file metadata, resolution breakdown,
        aspect ratio analysis, preview path, and any warnings.
    """
    in_p = Path(input_path).resolve()
    if not in_p.is_file():
        raise FileNotFoundError(f"Source image not found: {input_path}")

    out_p = Path(output_path).resolve()
    if in_p == out_p:
        raise ValueError("Destination output_path cannot be identical to source input_path")

    if out_p.exists() and not overwrite:
        raise FileExistsError(f"Destination output_path already exists: {output_path}")

    # Inspect source image
    with Image.open(in_p) as src_im:
        src_w, src_h = src_im.size
        src_mode = src_im.mode
        src_format = src_im.format or "PNG"
        src_icc_bytes = src_im.info.get("icc_profile")
        src_color_info = extract_color_profile(src_im)

    # Calculate target dimensions
    target_w_in, target_h_in, target_w_px, target_h_px, applied_orient = compute_print_target_dimensions(
        width_in=width_in,
        height_in=height_in,
        ppi=ppi,
        source_width=src_w,
        source_height=src_h,
        orientation=orientation,
    )

    # Aspect ratio comparison
    src_aspect = determine_aspect_ratio(src_w, src_h)
    tgt_aspect = determine_aspect_ratio(target_w_px, target_h_px)

    src_ratio = src_w / src_h if src_h else 0.0
    tgt_ratio = target_w_px / target_h_px if target_h_px else 0.0
    ratios_match = abs(src_ratio - tgt_ratio) < 0.015

    # Determine fit mode
    fit_req = fit_mode.lower()
    if fit_req in ("margins", "fit"):
        applied_fit_mode = "margins"
    elif fit_req in ("borderless", "crop"):
        applied_fit_mode = "borderless"
    elif fit_req == "auto":
        applied_fit_mode = "borderless" if ratios_match else "borderless"
    else:
        raise ValueError(
            f"Unsupported fit_mode '{fit_mode}'. Expected 'auto', 'borderless', 'crop', 'margins', or 'fit'."
        )

    sheet_dim1 = min(width_in, height_in)
    sheet_dim2 = max(width_in, height_in)
    sheet_label = f"{sheet_dim1:g}×{sheet_dim2:g}"

    src_label = src_aspect.get("standard_label") or src_aspect.get("simplified_ratio") or f"{src_w}:{src_h}"
    tgt_label = tgt_aspect.get("standard_label") or tgt_aspect.get("simplified_ratio") or f"{target_w_px}:{target_h_px}"

    # Clarification Gate:
    # If ratios conflict, and borderless/crop is targeted without explicit confirmation:
    if not ratios_match and applied_fit_mode == "borderless" and not confirm_crop:
        question = (
            f"Should the photo fill the {sheet_label} sheet with a {tgt_label} crop, "
            f"or keep the {src_label} crop and add margins?"
        )
        return {
            "ok": False,
            "status": "needs_clarification",
            "question": question,
            "sheet_size": sheet_label,
            "source_aspect_ratio": src_label,
            "target_aspect_ratio": tgt_label,
            "source_dimensions_px": [src_w, src_h],
            "target_dimensions_px": [target_w_px, target_h_px],
            "target_dimensions_in": [target_w_in, target_h_in],
            "fit_mode_requested": fit_mode,
            "message": f"Print request requires clarification: {question}",
        }

    # Resolution analysis
    effective_source_ppi = calculate_effective_source_ppi(
        source_width=src_w,
        source_height=src_h,
        target_width_in=target_w_in,
        target_height_in=target_h_in,
        fit_mode=applied_fit_mode,
    )

    warnings: List[str] = []
    needs_upscale = (src_w < target_w_px) or (src_h < target_h_px) or (effective_source_ppi < float(ppi))
    if needs_upscale:
        if not allow_upscale:
            raise ValueError(
                f"Source resolution ({effective_source_ppi:.1f} effective PPI, {src_w}×{src_h} px) "
                f"is lower than target print resolution ({ppi} PPI, {target_w_px}×{target_h_px} px). "
                f"Set allow_upscale=True to permit upscaling."
            )
        warnings.append(
            f"Low source resolution: effective source resolution is {effective_source_ppi:.1f} PPI "
            f"(target is {ppi} PPI, {target_w_px}×{target_h_px} px). Print quality may show softness "
            f"or pixelation; enlargement or restoration advised."
        )

    # Master copy preservation if requested
    saved_master_path: Optional[str] = None
    if preserve_master_path is not None:
        master_p = Path(preserve_master_path).resolve()
        if master_p == in_p:
            raise ValueError("preserve_master_path cannot be identical to source input_path")
        if master_p == out_p:
            raise ValueError("preserve_master_path cannot be identical to output_path")
        master_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(in_p, master_p)
        if sha256_file(str(master_p)) != sha256_file(str(in_p)):
            raise RuntimeError(f"Master copy checksum verification failed for {master_p}")
        saved_master_path = str(master_p)

    # Determine output format
    fmt_req = output_format.upper() if output_format else "AUTO"
    if fmt_req == "AUTO":
        ext = out_p.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            out_fmt = "JPEG"
        elif ext in (".tif", ".tiff"):
            out_fmt = "TIFF"
        else:
            out_fmt = "PNG"
    elif fmt_req in ("PNG", "TIFF", "JPEG"):
        out_fmt = fmt_req
    else:
        raise ValueError(f"Unsupported output_format '{output_format}'. Expected 'PNG', 'TIFF', or 'JPEG'.")

    # Render image strictly preserving proportions
    with Image.open(in_p) as full_img:
        # Working copy in memory
        working_img = full_img.copy()

    if applied_fit_mode == "margins":
        # Full-picture margins: fit inside target canvas preserving whole image
        scale = min(target_w_px / src_w, target_h_px / src_h)
        scaled_w = min(max(1, round(src_w * scale)), target_w_px)
        scaled_h = min(max(1, round(src_h * scale)), target_h_px)
        resized = working_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        canvas_mode = "RGBA" if (working_img.mode == "RGBA" and out_fmt != "JPEG") else "RGB"
        if resized.mode != canvas_mode:
            resized = resized.convert(canvas_mode)

        margin_rgb = parse_margin_color(margin_color)
        if canvas_mode == "RGB" and len(margin_rgb) == 4:
            margin_rgb = margin_rgb[:3]
        elif canvas_mode == "RGBA" and len(margin_rgb) == 3:
            margin_rgb = (*margin_rgb, 255)

        canvas = Image.new(canvas_mode, (target_w_px, target_h_px), margin_rgb)
        offset_x = (target_w_px - scaled_w) // 2
        offset_y = (target_h_px - scaled_h) // 2
        canvas.paste(resized, (offset_x, offset_y))
        final_delivery_img = canvas
    else:
        # Borderless: crop to fill sheet without margins
        scale = max(target_w_px / src_w, target_h_px / src_h)
        scaled_w = max(target_w_px, math.ceil(src_w * scale))
        scaled_h = max(target_h_px, math.ceil(src_h * scale))
        resized = working_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        crop_x = (scaled_w - target_w_px) // 2
        crop_y = (scaled_h - target_h_px) // 2
        cropped = resized.crop((crop_x, crop_y, crop_x + target_w_px, crop_y + target_h_px))

        if out_fmt == "JPEG" and cropped.mode != "RGB":
            cropped = cropped.convert("RGB")
        final_delivery_img = cropped

    # Color profile handling
    out_icc_bytes: Optional[bytes] = None
    if target_icc:
        target_icc_path = Path(target_icc)
        if target_icc_path.is_file():
            out_icc_bytes = target_icc_path.read_bytes()
        elif target_icc.lower() == "srgb":
            srgb_prof = ImageCms.createProfile("sRGB")
            out_icc_bytes = ImageCms.ImageCmsProfile(srgb_prof).tobytes()
        else:
            raise ValueError(f"Specified target_icc file not found: {target_icc}")
    else:
        out_icc_bytes = src_icc_bytes

    # Prepare save arguments
    save_kwargs: Dict[str, Any] = {
        "dpi": (float(ppi), float(ppi)) if out_fmt == "TIFF" else (ppi, ppi)
    }
    if out_fmt == "JPEG":
        save_kwargs["quality"] = 95
    if out_icc_bytes:
        save_kwargs["icc_profile"] = out_icc_bytes

    out_p.parent.mkdir(parents=True, exist_ok=True)
    final_delivery_img.save(out_p, format=out_fmt, **save_kwargs)

    # Verify exact delivery file by reopening and decoding
    with Image.open(out_p) as delivery:
        delivery.load()
        actual_w, actual_h = delivery.size
        actual_fmt = delivery.format or out_fmt
        actual_mode = delivery.mode
        actual_dpi = delivery.info.get("dpi")
        actual_icc = delivery.info.get("icc_profile")
        delivery_color_info = extract_color_profile(delivery)

    if actual_w != target_w_px or actual_h != target_h_px:
        raise RuntimeError(
            f"Delivery file dimension mismatch: expected ({target_w_px}, {target_h_px}), "
            f"got ({actual_w}, {actual_h})"
        )

    if actual_fmt.upper() != out_fmt.upper():
        raise RuntimeError(
            f"Delivery format mismatch: expected {out_fmt}, got {actual_fmt}"
        )

    delivery_dpi_x = round(actual_dpi[0], 1) if actual_dpi else None
    delivery_dpi_y = round(actual_dpi[1], 1) if actual_dpi else None

    # Generate visual composition preview
    if preview_path is not None:
        prev_p = Path(preview_path).resolve()
    else:
        prev_p = out_p.with_stem(out_p.stem + "_preview").with_suffix(".png")

    prev_p.parent.mkdir(parents=True, exist_ok=True)
    prev_img = final_delivery_img.copy()
    if max(prev_img.size) > max_preview_dimension:
        prev_img.thumbnail((max_preview_dimension, max_preview_dimension), Image.Resampling.LANCZOS)
    if prev_img.mode not in ("RGB", "RGBA"):
        prev_img = prev_img.convert("RGB")
    prev_img.save(prev_p, format="PNG")
    prev_w, prev_h = prev_img.size

    delivery_sha256 = sha256_file(str(out_p))
    delivery_byte_size = out_p.stat().st_size

    return {
        "ok": True,
        "status": "prepared",
        "delivery_file": {
            "path": str(out_p),
            "format": actual_fmt,
            "width_px": actual_w,
            "height_px": actual_h,
            "width_in": target_w_in,
            "height_in": target_h_in,
            "dpi": [delivery_dpi_x, delivery_dpi_y] if delivery_dpi_x else None,
            "export_ppi": ppi,
            "export_width_px": target_w_px,
            "export_height_px": target_h_px,
            "effective_source_ppi": effective_source_ppi,
            "color_mode": actual_mode,
            "sha256": delivery_sha256,
            "byte_size": delivery_byte_size,
            "color_profile": delivery_color_info,
        },
        "preview_path": str(prev_p),
        "preview_dimensions": [prev_w, prev_h],
        "fit_mode_applied": applied_fit_mode,
        "orientation_applied": applied_orient,
        "sheet_size": sheet_label,
        "aspect_ratio": {
            "source": src_aspect,
            "target": tgt_aspect,
            "ratios_match": ratios_match,
        },
        "effective_source_ppi": effective_source_ppi,
        "export_ppi": ppi,
        "export_width_px": target_w_px,
        "export_height_px": target_h_px,
        "warnings": warnings,
        "master_copy_path": saved_master_path,
    }
