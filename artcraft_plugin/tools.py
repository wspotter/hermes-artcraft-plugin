"""Hermes tool handlers for the ArtCraft plugin."""

from __future__ import annotations

import json
from typing import Any, Dict

from .discovery import discover_all
from .inspect import prepare_inspection
from .print_prep import prepare_print
from .runner import run_artcraft_cli, spot_heal
from .verify import inspect_image, verify_edit


def artcraft_status(args: Dict[str, Any], **kwargs: Any) -> str:
    """Return discovered ArtCraft CLI binaries and versions as JSON."""
    try:
        discovered = discover_all()
        return json.dumps(
            {
                "ok": True,
                "apps": {name: info.to_dict() for name, info in discovered.items()},
            }
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_inspect(args: Dict[str, Any], **kwargs: Any) -> str:
    """Inspect an image file and return metadata as JSON."""
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        return json.dumps({"ok": False, "error": "Missing required 'path' string"})
    try:
        info = inspect_image(path)
        return json.dumps({"ok": bool(info.get("valid")), **info})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_prepare_inspection(args: Dict[str, Any], **kwargs: Any) -> str:
    """Prepare whole-photo preview, native crops, print PPI, and measured clues."""
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        return json.dumps({"ok": False, "error": "Missing required 'path' string"})
    try:
        working_dir = args.get("working_dir")
        max_preview_dimension = args.get("max_preview_dimension", 1024)
        crop_size = args.get("crop_size", 256)
        regions = args.get("regions")
        target_print_sizes = args.get("target_print_sizes")
        result = prepare_inspection(
            path,
            working_dir=working_dir,
            max_preview_dimension=max_preview_dimension,
            crop_size=crop_size,
            regions=regions,
            target_print_sizes=target_print_sizes,
        )
        return json.dumps({"ok": bool(result.get("valid")), **result})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_verify_edit(args: Dict[str, Any], **kwargs: Any) -> str:
    """Verify an edited image against its input and return JSON."""
    input_path = args.get("input_path")
    output_path = args.get("output_path")
    if not isinstance(input_path, str) or not isinstance(output_path, str):
        return json.dumps({"passed": False, "error": "Need input_path and output_path strings"})
    try:
        result = verify_edit(
            input_path,
            output_path,
            expected_width=args.get("expected_width"),
            expected_height=args.get("expected_height"),
            region=args.get("region"),
            require_pixel_change=args.get("require_pixel_change", True),
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"passed": False, "error": str(exc)})


def _run_app_cli(app: str, args: Dict[str, Any]) -> str:
    cli_args = args.get("cli_args")
    if cli_args not in (["--help"], ["--version"]):
        return json.dumps({"ok": False, "error": "Only --help and --version are supported"})
    try:
        return json.dumps(run_artcraft_cli(app, cli_args))
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def photocraft_run(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run photocraft-cli with guards and verification."""
    return _run_app_cli("photocraft", args)


def lightcraft_run(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run lightcraft-cli with guards and verification."""
    return _run_app_cli("lightcraft", args)


def photocraft_spot_heal(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run the verified spot-heal workflow."""
    try:
        timeout_s = args.get("timeout_s", 120.0)
        return json.dumps(
            spot_heal(
                *(args[key] for key in (
                    "input_path", "output_path", "points", "size", "region",
                )),
                timeout_s=timeout_s,
            )
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_prepare_print(args: Dict[str, Any], **kwargs: Any) -> str:
    """Prepare a verified print delivery file or return clarification needed."""
    try:
        input_path = args.get("input_path")
        output_path = args.get("output_path")
        width_in = args.get("width_in")
        height_in = args.get("height_in")

        if not isinstance(input_path, str) or not input_path.strip():
            return json.dumps({"ok": False, "error": "Missing required 'input_path' string"})
        if not isinstance(output_path, str) or not output_path.strip():
            return json.dumps({"ok": False, "error": "Missing required 'output_path' string"})
        if width_in is None or height_in is None:
            return json.dumps({"ok": False, "error": "Missing required 'width_in' or 'height_in'"})

        result = prepare_print(
            input_path=input_path,
            output_path=output_path,
            width_in=float(width_in),
            height_in=float(height_in),
            orientation=args.get("orientation", "auto"),
            fit_mode=args.get("fit_mode", "auto"),
            confirm_crop=bool(args.get("confirm_crop", False)),
            ppi=int(args.get("ppi", 300)),
            output_format=args.get("output_format", "auto"),
            margin_color=args.get("margin_color", "white"),
            preserve_master_path=args.get("preserve_master_path"),
            allow_upscale=bool(args.get("allow_upscale", False)),
            target_icc=args.get("target_icc"),
            preview_path=args.get("preview_path"),
            overwrite=bool(args.get("overwrite", False)),
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})

