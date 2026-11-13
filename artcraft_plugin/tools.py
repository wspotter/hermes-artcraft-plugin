"""Hermes tool handlers for the ArtCraft plugin."""

from __future__ import annotations

import json
from typing import Any, Dict

from .discovery import discover_all
from .runner import run_artcraft_cli
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
    if not isinstance(cli_args, list) or not all(isinstance(x, str) for x in cli_args):
        return json.dumps({"ok": False, "error": "cli_args must be a list of strings"})
    try:
        result = run_artcraft_cli(
            app,
            cli_args,
            input_path=args.get("input_path"),
            output_path=args.get("output_path"),
            expected_width=args.get("expected_width"),
            expected_height=args.get("expected_height"),
            region=args.get("region"),
            verify=bool(args.get("verify", True)),
            timeout_s=float(args.get("timeout_s", 120.0)),
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def photocraft_run(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run photocraft-cli with guards and verification."""
    return _run_app_cli("photocraft", args)


def lightcraft_run(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run lightcraft-cli with guards and verification."""
    return _run_app_cli("lightcraft", args)
