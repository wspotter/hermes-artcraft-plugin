"""Print preparation helpers for the ArtCraft plugin.

Sizes and lays out source images for target physical dimensions and PPI while
preserving aspect ratio, ICC color profiles, and source/export PPI separation.
"""

from __future__ import annotations

import math
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageCms, ImageColor

from .inspect import determine_aspect_ratio, determine_orientation, extract_color_profile
from .runner import _paths_refer_to_same_file, atomic_replace_file
from .verify import sha256_file


def _validate_positive_print_params(width_in: float, height_in: float, ppi: int) -> None:
    """Validate that sheet dimensions and PPI are positive finite numbers."""
    if (
        isinstance(width_in, bool)
        or isinstance(height_in, bool)
        or not math.isfinite(width_in)
        or not math.isfinite(height_in)
        or width_in <= 0
        or height_in <= 0
    ):
        raise ValueError(
            f"Print dimensions must be positive, got width={width_in}, height={height_in}"
        )
    if isinstance(ppi, bool) or not math.isfinite(ppi) or ppi <= 0:
        raise ValueError(f"PPI must be positive, got ppi={ppi}")


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
    _validate_positive_print_params(width_in, height_in, ppi)

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
        if len(color_spec) not in (3, 4) or any(
            not isinstance(c, int) or isinstance(c, bool) or not (0 <= c <= 255)
            for c in color_spec
        ):
            raise ValueError(f"Unsupported margin_color: {color_spec!r}")
        return tuple(color_spec)
    if not isinstance(color_spec, str):
        raise ValueError(f"Unsupported margin_color: {color_spec!r}")

    color_clean = color_spec.strip()
    if not color_clean:
        raise ValueError(f"Unsupported margin_color: {color_spec!r}")
    if color_clean.lower() == "transparent":
        return (0, 0, 0, 0)
    try:
        return ImageColor.getrgb(color_clean)
    except Exception as exc:
        raise ValueError(f"Unsupported margin_color: {color_spec!r}") from exc


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
    allow_overwrite: bool = False,
    overwrite: Optional[bool] = None,
) -> Dict[str, Any]:
    """Prepare a print output file from a source image.

    Returns ``status: "needs_clarification"`` without writing an output file if
    borderless fit would crop a mismatched aspect ratio without ``confirm_crop=True``.
    """
    _validate_positive_print_params(width_in, height_in, ppi)
    effective_overwrite = bool(allow_overwrite or overwrite)

    in_p = Path(input_path).expanduser().resolve()
    if not in_p.is_file():
        raise FileNotFoundError(f"Source image not found: {input_path}")

    out_p = Path(os.path.abspath(Path(output_path).expanduser()))
    if _paths_refer_to_same_file(in_p, out_p):
        raise ValueError("Destination output_path cannot be identical to source input_path")

    if os.path.lexists(out_p) and not effective_overwrite:
        raise FileExistsError(f"Destination output_path already exists: {output_path}")

    with Image.open(in_p) as src_im:
        src_w, src_h = src_im.size
        src_icc_bytes = src_im.info.get("icc_profile")

    target_w_in, target_h_in, target_w_px, target_h_px, applied_orient = (
        compute_print_target_dimensions(
            width_in=width_in,
            height_in=height_in,
            ppi=ppi,
            source_width=src_w,
            source_height=src_h,
            orientation=orientation,
        )
    )

    src_aspect = determine_aspect_ratio(src_w, src_h)
    tgt_aspect = determine_aspect_ratio(target_w_px, target_h_px)

    src_ratio = src_w / src_h if src_h else 0.0
    tgt_ratio = target_w_px / target_h_px if target_h_px else 0.0
    ratios_match = abs(src_ratio - tgt_ratio) < 0.015

    fit_req = fit_mode.lower()
    if fit_req in ("margins", "fit"):
        applied_fit_mode = "margins"
    elif fit_req in ("borderless", "crop", "auto"):
        applied_fit_mode = "borderless"
    else:
        raise ValueError(
            f"Unsupported fit_mode '{fit_mode}'. "
            "Expected 'auto', 'borderless', 'crop', 'margins', or 'fit'."
        )

    sheet_dim1 = min(width_in, height_in)
    sheet_dim2 = max(width_in, height_in)
    sheet_label = f"{sheet_dim1:g}×{sheet_dim2:g}"

    src_label = (
        src_aspect.get("standard_label")
        or src_aspect.get("simplified_ratio")
        or f"{src_w}:{src_h}"
    )
    tgt_label = (
        tgt_aspect.get("standard_label")
        or tgt_aspect.get("simplified_ratio")
        or f"{target_w_px}:{target_h_px}"
    )

    # Ask before cropping if borderless fit would trim a mismatched aspect ratio
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

    effective_source_ppi = calculate_effective_source_ppi(
        source_width=src_w,
        source_height=src_h,
        target_width_in=target_w_in,
        target_height_in=target_h_in,
        fit_mode=applied_fit_mode,
    )

    warnings: List[str] = []
    if applied_fit_mode == "margins":
        margin_scale = min(target_w_px / src_w, target_h_px / src_h)
        needs_upscale = (effective_source_ppi < float(ppi)) or (margin_scale > 1.0)
    else:
        needs_upscale = (
            (effective_source_ppi < float(ppi))
            or (src_w < target_w_px)
            or (src_h < target_h_px)
        )
    if needs_upscale:
        if not allow_upscale:
            raise ValueError(
                f"Source resolution ({effective_source_ppi:.1f} effective PPI, {src_w}×{src_h} px) "
                f"is lower than target print resolution ({ppi} PPI, "
                f"{target_w_px}×{target_h_px} px). Set allow_upscale=True to permit upscaling."
            )
        warnings.append(
            f"Low source resolution: effective source resolution is {effective_source_ppi:.1f} PPI "
            f"(target is {ppi} PPI, {target_w_px}×{target_h_px} px). Print quality may show "
            "softness or pixelation; enlargement or restoration advised."
        )

    margin_rgb: Optional[Tuple[int, ...]] = None
    if applied_fit_mode == "margins":
        margin_rgb = parse_margin_color(margin_color)

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
        raise ValueError(
            f"Unsupported output_format '{output_format}'. Expected 'PNG', 'TIFF', or 'JPEG'."
        )

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

    if preview_path is not None:
        prev_p = Path(os.path.abspath(Path(preview_path).expanduser()))
    else:
        prev_p = out_p.with_stem(out_p.stem + "_preview").with_suffix(".png")

    if _paths_refer_to_same_file(in_p, prev_p) or _paths_refer_to_same_file(out_p, prev_p):
        raise ValueError("preview_path must be distinct from input_path and output_path")

    saved_master_path: Optional[str] = None
    if preserve_master_path is not None:
        master_p = Path(os.path.abspath(Path(preserve_master_path).expanduser()))
        if _paths_refer_to_same_file(in_p, master_p):
            raise ValueError("preserve_master_path cannot be identical to source input_path")
        if _paths_refer_to_same_file(out_p, master_p):
            raise ValueError("preserve_master_path cannot be identical to output_path")
        if _paths_refer_to_same_file(prev_p, master_p):
            raise ValueError("preserve_master_path cannot be identical to preview_path")

        in_sha = sha256_file(in_p)
        need_master_copy = True
        if os.path.lexists(master_p):
            if os.path.islink(master_p) and not master_p.exists():
                if not effective_overwrite:
                    raise FileExistsError(
                        f"Master copy path already exists (dangling symlink): "
                        f"{preserve_master_path}"
                    )
            elif master_p.is_file():
                if sha256_file(master_p) == in_sha:
                    need_master_copy = bool(os.path.islink(master_p) and effective_overwrite)
                elif not effective_overwrite:
                    raise FileExistsError(
                        f"Master copy path already exists with different content: "
                        f"{preserve_master_path}"
                    )
            else:
                raise FileExistsError(
                    f"Master copy path already exists and is not a regular file: "
                    f"{preserve_master_path}"
                )

        if need_master_copy:
            master_p.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".artcraft-master-", dir=master_p.parent) as m_tmp_dir:
                tmp_master = Path(m_tmp_dir) / (master_p.name or "master")
                shutil.copy2(in_p, tmp_master)
                if sha256_file(tmp_master) != in_sha:
                    raise RuntimeError(f"Master copy checksum verification failed for {master_p}")
                atomic_replace_file(tmp_master, master_p, allow_overwrite=effective_overwrite)
        saved_master_path = str(master_p.resolve())

    with Image.open(in_p) as full_img:
        working_img = full_img.copy()

    if applied_fit_mode == "margins":
        assert margin_rgb is not None
        # Full-picture margins: fit inside target canvas preserving whole image
        scale = min(target_w_px / src_w, target_h_px / src_h)
        scaled_w = min(max(1, round(src_w * scale)), target_w_px)
        scaled_h = min(max(1, round(src_h * scale)), target_h_px)
        resized = working_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        canvas_mode = "RGBA" if (working_img.mode == "RGBA" and out_fmt != "JPEG") else "RGB"
        if resized.mode != canvas_mode:
            resized = resized.convert(canvas_mode)

        resolved_margin = margin_rgb
        if canvas_mode == "RGB" and len(resolved_margin) == 4:
            resolved_margin = resolved_margin[:3]
        elif canvas_mode == "RGBA" and len(resolved_margin) == 3:
            resolved_margin = (*resolved_margin, 255)

        canvas = Image.new(canvas_mode, (target_w_px, target_h_px), resolved_margin)
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

    save_kwargs: Dict[str, Any] = {
        "dpi": (float(ppi), float(ppi)) if out_fmt == "TIFF" else (ppi, ppi)
    }
    if out_fmt == "JPEG":
        save_kwargs["quality"] = 95
    if out_icc_bytes:
        save_kwargs["icc_profile"] = out_icc_bytes

    out_p.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_p.suffix or f".{out_fmt.lower()}"
    with TemporaryDirectory(prefix=".artcraft-print-", dir=out_p.parent) as tmp_dir:
        tmp_out = Path(tmp_dir) / f"delivery{suffix}"
        final_delivery_img.save(tmp_out, format=out_fmt, **save_kwargs)

        # Reopen staged file to verify dimensions and format before promoting
        with Image.open(tmp_out) as delivery:
            delivery.load()
            actual_w, actual_h = delivery.size
            actual_fmt = delivery.format or out_fmt
            actual_mode = delivery.mode
            actual_dpi = delivery.info.get("dpi")
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

        atomic_replace_file(tmp_out, out_p, allow_overwrite=effective_overwrite)

    delivery_dpi_x = round(actual_dpi[0], 1) if actual_dpi else None
    delivery_dpi_y = round(actual_dpi[1], 1) if actual_dpi else None

    # Generate visual composition preview (prev_p validated earlier before disk writes)
    prev_p.parent.mkdir(parents=True, exist_ok=True)
    prev_img = final_delivery_img.copy()
    if max(prev_img.size) > max_preview_dimension:
        prev_img.thumbnail(
            (max_preview_dimension, max_preview_dimension), Image.Resampling.LANCZOS
        )
    if prev_img.mode not in ("RGB", "RGBA"):
        prev_img = prev_img.convert("RGB")
    with TemporaryDirectory(prefix=".artcraft-prev-", dir=prev_p.parent) as prev_tmp_dir:
        tmp_prev = Path(prev_tmp_dir) / "preview.png"
        prev_img.save(tmp_prev, format="PNG")
        atomic_replace_file(tmp_prev, prev_p, allow_overwrite=True)
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
