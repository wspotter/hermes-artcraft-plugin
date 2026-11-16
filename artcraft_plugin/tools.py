"""Hermes tool handlers for the ArtCraft plugin."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Optional

from .discovery import status_payload
from .inspect import prepare_inspection
from .jobs import (
    get_job,
    init_job,
    reconcile_delivery,
    record_delivery,
    record_export_artifact,
    resume_job,
    save_checkpoint,
)
from .print_prep import prepare_print
from .restore import get_checkpoint, list_checkpoints, restore_step
from .review import build_review_package
from .runner import run_artcraft_cli, spot_heal
from .suite_basics import (
    filmcraft_video_basic,
    lightcraft_develop,
    soundcraft_audio_basic,
)
from .verify import inspect_image, verify_edit


def _parse_positive_int(value: Any, default: Optional[int], name: str) -> int:
    """Parse a positive integer argument, rejecting booleans, non-integers, and <= 0."""
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"Missing required '{name}'")
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise ValueError(f"'{name}' must be a positive integer")
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"'{name}' must be a positive integer")
    return parsed


def _parse_positive_float(value: Any, default: Optional[float], name: str) -> float:
    """Parse a finite positive float argument, rejecting booleans, NaN/Inf, and <= 0."""
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"Missing required '{name}'")
    if isinstance(value, bool):
        raise ValueError(f"'{name}' must be a positive number")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"'{name}' must be a positive number")
    return parsed


def artcraft_status(args: Dict[str, Any], **kwargs: Any) -> str:
    """Return discovered ArtCraft CLI binaries, versions, and tool availability as JSON."""
    try:
        return json.dumps(status_payload())
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
    """Prepare whole-photo preview, native crops, print PPI, and image metrics."""
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
    """Run photocraft-cli --help or --version."""
    return _run_app_cli("photocraft", args)


def lightcraft_run(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run lightcraft-cli --help or --version."""
    return _run_app_cli("lightcraft", args)


def photocraft_spot_heal(args: Dict[str, Any], **kwargs: Any) -> str:
    """Run the verified spot-heal workflow."""
    try:
        timeout_s = _parse_positive_float(args.get("timeout_s"), 120.0, "timeout_s")
        return json.dumps(
            spot_heal(
                input_path=args["input_path"],
                output_path=args["output_path"],
                points=args["points"],
                size=args["size"],
                region=args["region"],
                timeout_s=timeout_s,
            )
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_prepare_print(args: Dict[str, Any], **kwargs: Any) -> str:
    """Prepare a print output file or return a clarification prompt."""
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

        width_val = _parse_positive_float(width_in, None, "width_in")
        height_val = _parse_positive_float(height_in, None, "height_in")
        ppi_val = _parse_positive_int(args.get("ppi"), 300, "ppi")
        allow_overwrite_raw = args.get("allow_overwrite")
        if allow_overwrite_raw is None:
            allow_overwrite_raw = args.get("overwrite", False)
        allow_overwrite = bool(allow_overwrite_raw)

        result = prepare_print(
            input_path=input_path,
            output_path=output_path,
            width_in=width_val,
            height_in=height_val,
            orientation=args.get("orientation", "auto"),
            fit_mode=args.get("fit_mode", "auto"),
            confirm_crop=bool(args.get("confirm_crop", False)),
            ppi=ppi_val,
            output_format=args.get("output_format", "auto"),
            margin_color=args.get("margin_color", "white"),
            preserve_master_path=args.get("preserve_master_path"),
            allow_upscale=bool(args.get("allow_upscale", False)),
            target_icc=args.get("target_icc"),
            preview_path=args.get("preview_path"),
            allow_overwrite=allow_overwrite,
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_restore_step(args: Dict[str, Any], **kwargs: Any) -> str:
    """Execute a single verified restoration step with checkpointing and crop comparisons."""
    try:
        input_path = args.get("input_path")
        output_path = args.get("output_path")
        recipe = args.get("recipe")
        if (
            not isinstance(input_path, str)
            or not input_path.strip()
            or not isinstance(output_path, str)
            or not output_path.strip()
            or not isinstance(recipe, str)
            or not recipe.strip()
        ):
            return json.dumps({
                "ok": False,
                "error": "Missing required 'input_path', 'output_path', or 'recipe'",
            })

        target_print_ppi = _parse_positive_int(
            args.get("target_print_ppi"), 300, "target_print_ppi"
        )
        timeout_s = _parse_positive_float(args.get("timeout_s"), 120.0, "timeout_s")

        result = restore_step(
            input_path=input_path,
            output_path=output_path,
            recipe=recipe,
            parameters=args.get("parameters"),
            region=args.get("region"),
            checkpoint_dir=args.get("checkpoint_dir"),
            step_name=args.get("step_name"),
            crop_regions=args.get("crop_regions"),
            target_print_ppi=target_print_ppi,
            reconstruct_missing=bool(args.get("reconstruct_missing", False)),
            content_type=args.get("content_type"),
            allow_overwrite=bool(args.get("allow_overwrite", False)),
            timeout_s=timeout_s,
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_checkpoint(args: Dict[str, Any], **kwargs: Any) -> str:
    """Inspect or list restoration checkpoints."""
    try:
        action = args.get("action", "list")
        checkpoint_dir = args.get("checkpoint_dir")
        if not checkpoint_dir:
            return json.dumps({"ok": False, "error": "Missing required 'checkpoint_dir'"})

        if action == "list":
            checkpoints = list_checkpoints(checkpoint_dir)
            return json.dumps({"ok": True, "checkpoints": checkpoints})
        elif action == "get":
            step_identifier = args.get("step_identifier")
            if step_identifier is None:
                return json.dumps({
                    "ok": False,
                    "error": "Missing 'step_identifier' for get action",
                })
            cp = get_checkpoint(checkpoint_dir, step_identifier)
            if cp is None:
                return json.dumps({
                    "ok": False,
                    "error": f"Checkpoint '{step_identifier}' not found",
                })
            return json.dumps({"ok": True, "checkpoint": cp})
        else:
            return json.dumps({"ok": False, "error": f"Unknown action: {action!r}"})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_build_review(args: Dict[str, Any], **kwargs: Any) -> str:
    """Build a review package for an image edit and run defect checks."""
    try:
        source_path = args.get("source_path")
        output_path = args.get("output_path")
        if not isinstance(source_path, str) or not source_path.strip():
            return json.dumps({
                "ok": False,
                "passed": False,
                "error": "Missing required 'source_path' string",
            })
        if not isinstance(output_path, str) or not output_path.strip():
            return json.dumps({
                "ok": False,
                "passed": False,
                "error": "Missing required 'output_path' string",
            })

        result = build_review_package(
            source_path=source_path,
            output_path=output_path,
            regions=args.get("regions"),
            region=args.get("region"),
            working_dir=args.get("working_dir"),
            max_preview_dimension=int(args.get("max_preview_dimension", 1024)),
            crop_size=int(args.get("crop_size", 256)),
            expected_aspect=args.get("expected_aspect"),
            preserve_framing=bool(args.get("preserve_framing", True)),
            crop_geometry=args.get("crop_geometry"),
            retry_count=int(args.get("retry_count", 0)),
            max_retries=int(args.get("max_retries", 3)),
            last_checkpoint_path=args.get("last_checkpoint_path"),
        )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"ok": False, "passed": False, "error": str(exc)})


def artcraft_job(args: Dict[str, Any], **kwargs: Any) -> str:
    """Manage job workspaces, checkpoints, exports, deliveries, and reconciliation."""
    action = args.get("action")
    job_id = args.get("job_id")
    if not isinstance(action, str) or not action.strip():
        return json.dumps({"ok": False, "error": "Missing required 'action' string"})
    if not isinstance(job_id, str) or not job_id.strip():
        return json.dumps({"ok": False, "error": "Missing required 'job_id' string"})

    workspace_dir = args.get("workspace_dir")
    try:
        if action == "init":
            res = init_job(
                job_id=job_id,
                source_path=args.get("source_path"),
                workspace_dir=workspace_dir,
                metadata=args.get("metadata"),
            )
            return json.dumps({"ok": True, "job": res})

        elif action == "checkpoint":
            stage = args.get("stage")
            file_path = args.get("file_path")
            if not stage or not file_path:
                return json.dumps({
                    "ok": False,
                    "error": "Checkpoint action requires 'stage' and 'file_path'",
                })
            res = save_checkpoint(
                job_id=job_id,
                stage=str(stage),
                file_path=str(file_path),
                verified=bool(args.get("verified", True)),
                workspace_dir=workspace_dir,
                metadata=args.get("metadata"),
            )
            return json.dumps(res)

        elif action == "resume":
            res = resume_job(job_id=job_id, workspace_dir=workspace_dir)
            return json.dumps(res)

        elif action == "export":
            artifact_id = args.get("artifact_id")
            file_path = args.get("file_path")
            if not artifact_id or not file_path:
                return json.dumps({
                    "ok": False,
                    "error": "Export action requires 'artifact_id' and 'file_path'",
                })
            res = record_export_artifact(
                job_id=job_id,
                artifact_id=str(artifact_id),
                file_path=str(file_path),
                verified=bool(args.get("verified", True)),
                workspace_dir=workspace_dir,
                metadata=args.get("metadata"),
            )
            return json.dumps(res)

        elif action == "deliver":
            destination = args.get("destination")
            artifact_id = args.get("artifact_id")
            if not destination or not artifact_id:
                return json.dumps({
                    "ok": False,
                    "error": "Deliver action requires 'destination' and 'artifact_id'",
                })
            res = record_delivery(
                job_id=job_id,
                destination=str(destination),
                artifact_id=str(artifact_id),
                status=str(args.get("status", "pending")),
                workspace_dir=workspace_dir,
                receipt_id=args.get("receipt_id"),
                notes=args.get("notes"),
            )
            return json.dumps(res)

        elif action == "reconcile":
            destination = args.get("destination")
            if not destination:
                return json.dumps({"ok": False, "error": "Reconcile action requires 'destination'"})
            res = reconcile_delivery(
                job_id=job_id,
                destination=str(destination),
                receipt_id=args.get("receipt_id"),
                confirmed_status=args.get("status"),
                workspace_dir=workspace_dir,
                notes=args.get("notes"),
            )
            return json.dumps(res)

        elif action == "status":
            job = get_job(job_id=job_id, workspace_dir=workspace_dir)
            return json.dumps({"ok": True, "job": job})

        else:
            return json.dumps({"ok": False, "error": f"Unknown job action '{action}'"})

    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def artcraft_develop(args: Dict[str, Any], **kwargs: Any) -> str:
    """Develop an image or raw file via LightCraft non-destructively."""
    try:
        input_path = args.get("input_path")
        output_path = args.get("output_path")
        if not isinstance(input_path, str) or not input_path.strip():
            return json.dumps({
                "ok": False,
                "app": "lightcraft",
                "error": "Missing required 'input_path' string",
            })
        if not isinstance(output_path, str) or not output_path.strip():
            return json.dumps({
                "ok": False,
                "app": "lightcraft",
                "error": "Missing required 'output_path' string",
            })

        res = lightcraft_develop(
            input_path=input_path,
            output_path=output_path,
            sliders=args.get("sliders"),
            preset=args.get("preset"),
            long_edge=args.get("long_edge"),
            quality=int(args.get("quality", 92)),
            export_options=args.get("export_options"),
            allow_overwrite=bool(args.get("allow_overwrite", False)),
            timeout_s=float(args.get("timeout_s", 120.0)),
        )
        return json.dumps(res)
    except Exception as exc:
        return json.dumps({"ok": False, "app": "lightcraft", "error": str(exc)})


def artcraft_audio_basic(args: Dict[str, Any], **kwargs: Any) -> str:
    """Probe or convert/normalize audio files via SoundCraft non-destructively."""
    try:
        action = args.get("action")
        input_path = args.get("input_path")
        if not isinstance(action, str) or not action.strip():
            return json.dumps({
                "ok": False,
                "app": "soundcraft",
                "error": "Missing required 'action' string",
            })
        if not isinstance(input_path, str) or not input_path.strip():
            return json.dumps({
                "ok": False,
                "app": "soundcraft",
                "error": "Missing required 'input_path' string",
            })

        res = soundcraft_audio_basic(
            action=action,
            input_path=input_path,
            output_path=args.get("output_path"),
            sample_rate=args.get("sample_rate"),
            bit_depth=args.get("bit_depth"),
            normalize=bool(args.get("normalize", False)),
            dither=args.get("dither"),
            allow_overwrite=bool(args.get("allow_overwrite", False)),
            timeout_s=float(args.get("timeout_s", 120.0)),
        )
        return json.dumps(res)
    except Exception as exc:
        return json.dumps({"ok": False, "app": "soundcraft", "error": str(exc)})


def artcraft_video_basic(args: Dict[str, Any], **kwargs: Any) -> str:
    """Probe media, extract still frames, or export video via FilmCraft non-destructively."""
    try:
        action = args.get("action")
        if not isinstance(action, str) or not action.strip():
            return json.dumps({
                "ok": False,
                "app": "filmcraft",
                "error": "Missing required 'action' string",
            })

        res = filmcraft_video_basic(
            action=action,
            input_path=args.get("input_path"),
            project_path=args.get("project_path"),
            demo=bool(args.get("demo", False)),
            output_path=args.get("output_path"),
            seconds=float(args.get("seconds", 0.0)),
            start_seconds=args.get("start_seconds"),
            end_seconds=args.get("end_seconds"),
            format=args.get("format"),
            preset=args.get("preset"),
            scale=args.get("scale"),
            quality=args.get("quality"),
            no_audio=bool(args.get("no_audio", False)),
            allow_overwrite=bool(args.get("allow_overwrite", False)),
            timeout_s=float(args.get("timeout_s", 180.0)),
        )
        return json.dumps(res)
    except Exception as exc:
        return json.dumps({"ok": False, "app": "filmcraft", "error": str(exc)})

