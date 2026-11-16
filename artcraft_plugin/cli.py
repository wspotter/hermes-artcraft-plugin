"""CLI subcommands registered under `hermes artcraft`."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

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
from .suite_basics import (
    filmcraft_video_basic,
    lightcraft_develop,
    soundcraft_audio_basic,
)
from .verify import verify_edit


def _require_positive(value: float | int, flag: str) -> None:
    if value <= 0:
        raise ValueError(f"{flag} must be positive")


def _cmd_doctor(_args: argparse.Namespace) -> int:
    payload = status_payload()
    print(json.dumps(payload, indent=2))
    return 0 if any(info.get("available") for info in payload["apps"].values()) else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        if args.width is not None:
            _require_positive(args.width, "--width")
        if args.height is not None:
            _require_positive(args.height, "--height")
        result = verify_edit(
            args.input_path,
            args.output_path,
            expected_width=args.width,
            expected_height=args.height,
            region=args.region,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("passed") else 1
    except Exception as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2))
        return 1


def _cmd_inspect(args: argparse.Namespace) -> int:
    try:
        _require_positive(args.preview_max, "--preview-max")
        _require_positive(args.crop_size, "--crop-size")
        result = prepare_inspection(
            args.path,
            working_dir=args.working_dir,
            max_preview_dimension=args.preview_max,
            crop_size=args.crop_size,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("valid") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "valid": False, "error": str(exc)}, indent=2))
        return 1


def _cmd_prep_print(args: argparse.Namespace) -> int:
    try:
        result = prepare_print(
            input_path=args.input_path,
            output_path=args.output_path,
            width_in=args.width_in,
            height_in=args.height_in,
            orientation=args.orientation,
            fit_mode=args.fit_mode,
            confirm_crop=args.confirm_crop,
            ppi=args.ppi,
            output_format=args.output_format,
            margin_color=args.margin_color,
            preserve_master_path=args.preserve_master_path,
            allow_upscale=args.allow_upscale,
            target_icc=args.target_icc,
            preview_path=args.preview_path,
            allow_overwrite=bool(getattr(args, "allow_overwrite", False)),
        )
        print(json.dumps(result, indent=2))
        return 0 if (result.get("ok") or result.get("status") == "needs_clarification") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1


def _cmd_restore(args: argparse.Namespace) -> int:
    try:
        params = json.loads(args.params) if args.params else None
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Invalid --params JSON: {exc}"}, indent=2))
        return 1

    try:
        _require_positive(args.ppi, "--ppi")
        result = restore_step(
            input_path=args.input_path,
            output_path=args.output_path,
            recipe=args.recipe,
            parameters=params,
            region=args.region,
            checkpoint_dir=args.checkpoint_dir,
            step_name=args.step_name,
            target_print_ppi=args.ppi,
            reconstruct_missing=args.reconstruct_missing,
            content_type=args.content_type,
            allow_overwrite=args.allow_overwrite,
        )
        print(json.dumps(result, indent=2))
        if result.get("status") == "needs_decision":
            return 2  # Operator confirmation required
        return 0 if result.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1


def _cmd_checkpoint(args: argparse.Namespace) -> int:
    try:
        if args.action == "list":
            cps = list_checkpoints(args.checkpoint_dir)
            print(json.dumps({"ok": True, "checkpoints": cps}, indent=2))
            return 0
        elif args.action == "get":
            if not args.step_id:
                print(json.dumps({"ok": False, "error": "--step-id required for get"}, indent=2))
                return 1
            cp = get_checkpoint(args.checkpoint_dir, args.step_id)
            if cp is None:
                print(json.dumps({"ok": False, "error": "Checkpoint not found"}, indent=2))
                return 1
            print(json.dumps({"ok": True, "checkpoint": cp}, indent=2))
            return 0
        else:
            print(json.dumps({"ok": False, "error": f"Unknown action {args.action}"}, indent=2))
            return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1


def _cmd_review(args: argparse.Namespace) -> int:
    try:
        _require_positive(args.preview_max, "--preview-max")
        _require_positive(args.crop_size, "--crop-size")
        if args.retry_count < 0 or args.max_retries < 0:
            raise ValueError("--retry-count and --max-retries must be non-negative")
        regions = None
        if getattr(args, "regions", None):
            regions = json.loads(args.regions)
        elif getattr(args, "region", None):
            regions = [args.region]

        result = build_review_package(
            source_path=args.source_path,
            output_path=args.output_path,
            regions=regions,
            working_dir=args.working_dir,
            max_preview_dimension=args.preview_max,
            crop_size=args.crop_size,
            expected_aspect=args.expected_aspect,
            preserve_framing=args.preserve_framing,
            crop_geometry=args.crop_geometry,
            retry_count=args.retry_count,
            max_retries=args.max_retries,
            last_checkpoint_path=args.last_checkpoint,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("passed") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "passed": False, "error": str(exc)}, indent=2))
        return 1


def _cmd_job(args: argparse.Namespace) -> int:
    try:
        action = args.job_action
        job_id = args.job_id
        workspace_dir = getattr(args, "workspace", None)

        if action == "init":
            meta = json.loads(args.meta) if getattr(args, "meta", None) else None
            res = init_job(
                job_id=job_id,
                source_path=getattr(args, "source", None),
                workspace_dir=workspace_dir,
                metadata=meta,
            )
            print(json.dumps({"ok": True, "job": res}, indent=2))
            return 0
        elif action == "checkpoint":
            meta = json.loads(args.meta) if getattr(args, "meta", None) else None
            res = save_checkpoint(
                job_id=job_id,
                stage=args.stage,
                file_path=args.file,
                verified=not getattr(args, "not_verified", False),
                workspace_dir=workspace_dir,
                metadata=meta,
            )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1
        elif action == "resume":
            res = resume_job(job_id=job_id, workspace_dir=workspace_dir)
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1
        elif action == "export":
            meta = json.loads(args.meta) if getattr(args, "meta", None) else None
            res = record_export_artifact(
                job_id=job_id,
                artifact_id=args.artifact_id,
                file_path=args.file,
                verified=not getattr(args, "not_verified", False),
                workspace_dir=workspace_dir,
                metadata=meta,
            )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1
        elif action == "deliver":
            res = record_delivery(
                job_id=job_id,
                destination=args.destination,
                artifact_id=args.artifact_id,
                status=getattr(args, "status", "pending"),
                workspace_dir=workspace_dir,
                receipt_id=getattr(args, "receipt_id", None),
                notes=getattr(args, "notes", None),
            )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1
        elif action == "reconcile":
            res = reconcile_delivery(
                job_id=job_id,
                destination=args.destination,
                receipt_id=getattr(args, "receipt_id", None),
                confirmed_status=getattr(args, "status", None),
                workspace_dir=workspace_dir,
                notes=getattr(args, "notes", None),
            )
            print(json.dumps(res, indent=2))
            return 0 if res.get("ok") else 1
        elif action == "status":
            job = get_job(job_id=job_id, workspace_dir=workspace_dir)
            print(json.dumps({"ok": True, "job": job}, indent=2))
            return 0
        else:
            print(json.dumps({"ok": False, "error": f"Unknown job action: {action}"}, indent=2))
            return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1


def _parse_kv_pairs(pairs: Any) -> dict:
    out: dict = {}
    if not pairs:
        return out
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Expected KEY=VALUE, got {item!r}")
        k, v_raw = item.split("=", 1)
        try:
            v = json.loads(v_raw)
        except Exception:
            v = v_raw
        out[k.strip()] = v
    return out


def _cmd_develop(args: argparse.Namespace) -> int:
    try:
        sliders = _parse_kv_pairs(getattr(args, "sliders", None))
        opts = _parse_kv_pairs(getattr(args, "opts", None))
        res = lightcraft_develop(
            input_path=args.input_path,
            output_path=args.output_path,
            sliders=sliders or None,
            preset=args.preset,
            long_edge=args.size,
            quality=args.quality,
            export_options=opts or None,
            allow_overwrite=args.allow_overwrite,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "app": "lightcraft", "error": str(exc)}, indent=2))
        return 1


def _cmd_audio(args: argparse.Namespace) -> int:
    try:
        dither = True if args.dither else (False if args.no_dither else None)
        res = soundcraft_audio_basic(
            action=args.action,
            input_path=args.input_path,
            output_path=args.output_path,
            sample_rate=args.rate,
            bit_depth=args.bit_depth,
            normalize=args.normalize,
            dither=dither,
            allow_overwrite=args.allow_overwrite,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "app": "soundcraft", "error": str(exc)}, indent=2))
        return 1


def _cmd_video(args: argparse.Namespace) -> int:
    try:
        res = filmcraft_video_basic(
            action=args.action,
            input_path=args.input_path,
            project_path=args.project_path,
            demo=args.demo,
            output_path=args.output_path,
            seconds=args.seconds,
            start_seconds=args.start_seconds,
            end_seconds=args.end_seconds,
            format=args.format,
            preset=args.preset,
            scale=args.scale,
            quality=args.quality,
            no_audio=args.no_audio,
            allow_overwrite=args.allow_overwrite,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "app": "filmcraft", "error": str(exc)}, indent=2))
        return 1


def _parse_recipe_param_value(raw_val: str) -> Any:
    """Parse CLI `--param key=value` scalar/JSON values safely."""
    low = raw_val.strip().lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null":
        return None
    try:
        return json.loads(raw_val)
    except Exception:
        return raw_val


def _parse_recipe_params(args: argparse.Namespace) -> dict[str, Any] | None:
    """Combine `--params-json` and repeated `--param key=value` CLI arguments."""
    merged: dict[str, Any] = {}
    if getattr(args, "params_json", None):
        parsed = json.loads(args.params_json)
        if not isinstance(parsed, dict):
            raise ValueError("--params-json must decode to a JSON object")
        merged.update(parsed)
    for item in getattr(args, "param", None) or []:
        if "=" not in item:
            raise ValueError(f"--param must use key=value format, got {item!r}")
        k, _, v = item.partition("=")
        key = k.strip()
        if not key:
            raise ValueError(f"Empty parameter key in {item!r}")
        merged[key] = _parse_recipe_param_value(v)
    return merged or None


def _cmd_recipe(args: argparse.Namespace) -> int:
    from .recipes import (
        export_recipe,
        import_recipe,
        init_recipe,
        list_recipes,
        run_recipe,
        validate_recipe,
    )

    try:
        action = args.recipe_action
        if action == "list":
            res = list_recipes(skills_dir=args.skills_dir)
        elif action == "init":
            res = init_recipe(
                args.slug,
                app=args.app,
                dest_dir=args.dest_dir,
                author=args.author,
                description=args.description,
                allow_overwrite=args.allow_overwrite,
            )
        elif action == "validate":
            res = validate_recipe(
                args.recipe,
                skills_dir=args.skills_dir,
                require_manifest=not args.allow_doc_only,
            )
        elif action == "export":
            res = export_recipe(
                args.recipe,
                args.archive_path,
                skills_dir=args.skills_dir,
                allow_overwrite=args.allow_overwrite,
            )
        elif action == "import":
            res = import_recipe(
                args.archive_path,
                dest_dir=args.dest_dir,
                allow_overwrite=args.allow_overwrite,
            )
        elif action == "run":
            res = run_recipe(
                args.recipe,
                args.input_path,
                args.output_path,
                params=_parse_recipe_params(args),
                work_dir=args.work_dir,
                skills_dir=args.skills_dir,
                allow_overwrite=args.allow_overwrite,
                dry_run=args.dry_run,
            )
        else:
            res = {"ok": False, "error": f"Unknown recipe subcommand: {action!r}"}

        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1





def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Register artcraft CLI subcommands on subparser."""
    sub = subparser.add_subparsers(dest="artcraft_cmd", required=True)

    doctor = sub.add_parser("doctor", help="Check installed ArtCraft CLI binaries")
    doctor.set_defaults(func=_cmd_doctor)

    verify = sub.add_parser("verify", help="Verify an edited image against its source")
    verify.add_argument("input_path", help="Original input image path")
    verify.add_argument("output_path", help="Edited output image path")
    verify.add_argument("--width", type=int, default=None, help="Expected output width")
    verify.add_argument("--height", type=int, default=None, help="Expected output height")
    verify.add_argument(
        "--region",
        type=int,
        nargs=4,
        metavar=("X", "Y", "W", "H"),
        default=None,
        help="Optional region [x y w h] that must show pixel changes",
    )
    verify.set_defaults(func=_cmd_verify)

    inspect_cmd = sub.add_parser(
        "inspect",
        help="Prepare preview, crops, and image metrics for visual inspection",
    )
    inspect_cmd.add_argument("path", help="Path to source image")
    inspect_cmd.add_argument(
        "--working-dir", default=None, help="Directory to save preview and crops"
    )
    inspect_cmd.add_argument(
        "--preview-max",
        type=int,
        default=1024,
        help="Maximum preview dimension (default 1024)",
    )
    inspect_cmd.add_argument(
        "--crop-size",
        type=int,
        default=256,
        help="Pixel size for native crops (default 256)",
    )
    inspect_cmd.set_defaults(func=_cmd_inspect)

    prep_cmd = sub.add_parser("prep-print", help="Prepare a print-ready output file")
    prep_cmd.add_argument("input_path", help="Path to source image")
    prep_cmd.add_argument("output_path", help="Path to destination print file")
    prep_cmd.add_argument(
        "--width",
        type=float,
        required=True,
        dest="width_in",
        help="Target print width in inches",
    )
    prep_cmd.add_argument(
        "--height",
        type=float,
        required=True,
        dest="height_in",
        help="Target print height in inches",
    )
    prep_cmd.add_argument(
        "--orientation",
        choices=["auto", "portrait", "landscape"],
        default="auto",
        help="Print orientation (default auto)",
    )
    prep_cmd.add_argument(
        "--fit-mode",
        choices=["auto", "borderless", "crop", "margins", "fit"],
        default="auto",
        help="Fit mode (default auto)",
    )
    prep_cmd.add_argument(
        "--confirm-crop",
        action="store_true",
        default=False,
        help="Confirm cropping if aspect ratio conflicts",
    )
    prep_cmd.add_argument("--ppi", type=int, default=300, help="Target export PPI (default 300)")
    prep_cmd.add_argument(
        "--format",
        dest="output_format",
        choices=["auto", "PNG", "TIFF", "JPEG"],
        default="auto",
        help="Output format (default auto)",
    )
    prep_cmd.add_argument(
        "--margin-color", default="white", help="Margin color for fit mode (default white)"
    )
    prep_cmd.add_argument(
        "--preserve-master",
        dest="preserve_master_path",
        default=None,
        help="Path to preserve master copy",
    )
    prep_cmd.add_argument(
        "--allow-upscale",
        action="store_true",
        default=False,
        help="Allow upscaling small images",
    )
    prep_cmd.add_argument(
        "--target-icc", default=None, help="Target ICC profile path or 'sRGB'"
    )
    prep_cmd.add_argument(
        "--preview-path", default=None, help="Explicit path for preview image"
    )
    prep_cmd.add_argument(
        "--allow-overwrite",
        action="store_true",
        default=False,
        help="Allow overwriting existing output",
    )
    prep_cmd.set_defaults(func=_cmd_prep_print)

    restore_cmd = sub.add_parser(
        "restore", help="Apply a restoration recipe with checkpointing and crops"
    )
    restore_cmd.add_argument(
        "recipe",
        choices=[
            "faded_tones",
            "color_cast",
            "dust_and_scratches",
            "noise_and_grain",
            "sharpening",
            "enlargement",
        ],
        help="Restoration recipe",
    )
    restore_cmd.add_argument("input_path", help="Path to input photo")
    restore_cmd.add_argument("output_path", help="Path to output photo")
    restore_cmd.add_argument("--params", default=None, help="JSON-encoded recipe parameters")
    restore_cmd.add_argument(
        "--region",
        type=int,
        nargs=4,
        metavar=("X", "Y", "W", "H"),
        default=None,
        help="Optional [x y w h] region",
    )
    restore_cmd.add_argument("--checkpoint-dir", default=None, help="Checkpoint directory")
    restore_cmd.add_argument("--step-name", default=None, help="Custom step name")
    restore_cmd.add_argument(
        "--ppi", type=int, default=300, help="Target print resolution PPI (default 300)"
    )
    restore_cmd.add_argument(
        "--reconstruct-missing",
        action="store_true",
        default=False,
        help="Reconstruct missing features (requires confirmation)",
    )
    restore_cmd.add_argument(
        "--content-type", default=None, help="Content type hint (e.g. missing_face)"
    )
    restore_cmd.add_argument(
        "--allow-overwrite",
        action="store_true",
        default=False,
        help="Allow overwriting output",
    )
    restore_cmd.set_defaults(func=_cmd_restore)

    cp_cmd = sub.add_parser("checkpoint", help="Manage restoration checkpoints")
    cp_cmd.add_argument("action", choices=["list", "get"], help="Checkpoint action")
    cp_cmd.add_argument("checkpoint_dir", help="Path to checkpoint directory")
    cp_cmd.add_argument("--step-id", default=None, help="Step index or name for get action")
    cp_cmd.set_defaults(func=_cmd_checkpoint)

    # Edit review
    rev_cmd = sub.add_parser("review", help="Build a review package and run defect checks")
    rev_cmd.add_argument("source_path", help="Path to original source photo")
    rev_cmd.add_argument("output_path", help="Path to edited output photo")
    rev_cmd.add_argument("--working-dir", default=None, help="Directory to save previews and crops")
    rev_cmd.add_argument(
        "--region",
        type=int,
        nargs=4,
        metavar=("X", "Y", "W", "H"),
        default=None,
        help="Target repair region [x y w h]",
    )
    rev_cmd.add_argument(
        "--regions",
        default=None,
        help="JSON-encoded list of repair regions [[x,y,w,h], ...]",
    )
    rev_cmd.add_argument(
        "--preview-max",
        type=int,
        default=1024,
        help="Max preview dimension in pixels (default 1024)",
    )
    rev_cmd.add_argument(
        "--crop-size",
        type=int,
        default=256,
        help="Native crop dimension in pixels (default 256)",
    )
    rev_cmd.add_argument(
        "--crop-geometry",
        type=json.loads,
        help="JSON crop rect or quad in source pixels",
    )
    rev_cmd.add_argument(
        "--expected-aspect",
        default=None,
        help="Optional expected aspect ratio (e.g. '4:5' or 0.8)",
    )
    rev_cmd.add_argument(
        "--no-preserve-framing",
        action="store_false",
        dest="preserve_framing",
        default=True,
        help="Allow aspect/framing shift from source",
    )
    rev_cmd.add_argument("--retry-count", type=int, default=0, help="Current retry count")
    rev_cmd.add_argument("--max-retries", type=int, default=3, help="Max retry limit")
    rev_cmd.add_argument("--last-checkpoint", default=None, help="Path to last verified checkpoint")
    rev_cmd.set_defaults(func=_cmd_review)

    # Job workspaces and delivery tracking
    job_cmd = sub.add_parser(
        "job", help="Manage job workspaces, checkpoints, and delivery receipts"
    )
    job_sub = job_cmd.add_subparsers(dest="job_action", required=True)

    j_init = job_sub.add_parser("init", help="Initialize a job workspace folder")
    j_init.add_argument("job_id", help="Unique job ID")
    j_init.add_argument("--source", default=None, help="Path to source image")
    j_init.add_argument("--workspace", default=None, help="Base workspace directory")
    j_init.add_argument("--meta", default=None, help="JSON-encoded metadata")
    j_init.set_defaults(func=_cmd_job)

    j_cp = job_sub.add_parser("checkpoint", help="Save a stage checkpoint")
    j_cp.add_argument("job_id", help="Unique job ID")
    j_cp.add_argument("--stage", required=True, help="Stage identifier")
    j_cp.add_argument("--file", required=True, help="Checkpoint file path")
    j_cp.add_argument(
        "--not-verified", action="store_true", default=False, help="Mark checkpoint unverified"
    )
    j_cp.add_argument("--workspace", default=None, help="Base workspace directory")
    j_cp.add_argument("--meta", default=None, help="JSON-encoded metadata")
    j_cp.set_defaults(func=_cmd_job)

    j_resume = job_sub.add_parser("resume", help="Resume from last verified checkpoint")
    j_resume.add_argument("job_id", help="Unique job ID")
    j_resume.add_argument("--workspace", default=None, help="Base workspace directory")
    j_resume.set_defaults(func=_cmd_job)

    j_export = job_sub.add_parser("export", help="Record verified export artifact")
    j_export.add_argument("job_id", help="Unique job ID")
    j_export.add_argument("--artifact-id", required=True, help="Unique artifact ID")
    j_export.add_argument("--file", required=True, help="Export artifact file path")
    j_export.add_argument(
        "--not-verified", action="store_true", default=False, help="Mark artifact unverified"
    )
    j_export.add_argument("--workspace", default=None, help="Base workspace directory")
    j_export.add_argument("--meta", default=None, help="JSON-encoded metadata")
    j_export.set_defaults(func=_cmd_job)

    j_deliver = job_sub.add_parser("deliver", help="Record delivery receipt")
    j_deliver.add_argument("job_id", help="Unique job ID")
    j_deliver.add_argument("--artifact-id", required=True, help="Export artifact ID to deliver")
    j_deliver.add_argument("--destination", required=True, help="Destination path or URI")
    j_deliver.add_argument(
        "--status",
        choices=["pending", "delivered", "uncertain"],
        default="pending",
        help="Delivery status",
    )
    j_deliver.add_argument("--receipt-id", default=None, help="Optional receipt ID")
    j_deliver.add_argument("--workspace", default=None, help="Base workspace directory")
    j_deliver.add_argument("--notes", default=None, help="Notes or delivery reason")
    j_deliver.set_defaults(func=_cmd_job)

    j_recon = job_sub.add_parser("reconcile", help="Reconcile uncertain delivery")
    j_recon.add_argument("job_id", help="Unique job ID")
    j_recon.add_argument("--destination", required=True, help="Destination path or URI")
    j_recon.add_argument("--receipt-id", default=None, help="Receipt ID to reconcile")
    j_recon.add_argument(
        "--status",
        choices=["delivered", "failed"],
        default=None,
        help="Explicit confirmation status",
    )
    j_recon.add_argument("--workspace", default=None, help="Base workspace directory")
    j_recon.add_argument("--notes", default=None, help="Reconciliation notes")
    j_recon.set_defaults(func=_cmd_job)

    j_status = job_sub.add_parser("status", help="Get job status")
    j_status.add_argument("job_id", help="Unique job ID")
    j_status.add_argument("--workspace", default=None, help="Base workspace directory")
    j_status.set_defaults(func=_cmd_job)

    dev_cmd = sub.add_parser("develop", help="Develop and export an image via LightCraft")
    dev_cmd.add_argument("input_path", help="Source image or raw path")
    dev_cmd.add_argument("output_path", help="Developed output path")
    dev_cmd.add_argument(
        "--set",
        dest="sliders",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Set develop slider (repeatable)",
    )
    dev_cmd.add_argument("--preset", default=None, help="Apply preset ID")
    dev_cmd.add_argument("--size", type=int, default=None, help="Output long edge in pixels")
    dev_cmd.add_argument(
        "--quality", type=int, default=92, help="Output quality 1..100 (default 92)"
    )
    dev_cmd.add_argument(
        "--opt",
        dest="opts",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Export option (repeatable)",
    )
    dev_cmd.add_argument(
        "--allow-overwrite",
        action="store_true",
        default=False,
        help="Allow overwriting existing output",
    )
    dev_cmd.set_defaults(func=_cmd_develop)

    aud_cmd = sub.add_parser("audio", help="Probe or convert/normalize audio via SoundCraft")
    aud_cmd.add_argument("action", choices=["info", "convert"], help="Audio action")
    aud_cmd.add_argument("input_path", help="Source audio file path")
    aud_cmd.add_argument(
        "output_path",
        nargs="?",
        default=None,
        help="Destination audio file path (required for convert)",
    )
    aud_cmd.add_argument("--rate", type=int, default=None, help="Target sample rate in Hz")
    aud_cmd.add_argument(
        "--bit-depth", choices=["16", "24", "32f"], default=None, help="Target bit depth"
    )
    aud_cmd.add_argument(
        "--normalize", action="store_true", default=False, help="Peak-normalize to -0.1 dBFS"
    )
    aud_cmd.add_argument("--dither", action="store_true", default=False, help="Always dither")
    aud_cmd.add_argument("--no-dither", action="store_true", default=False, help="Never dither")
    aud_cmd.add_argument(
        "--allow-overwrite",
        action="store_true",
        default=False,
        help="Allow overwriting existing output",
    )
    aud_cmd.set_defaults(func=_cmd_audio)

    vid_cmd = sub.add_parser(
        "video", help="Probe media, render frames, or export video via FilmCraft"
    )
    vid_cmd.add_argument(
        "action", choices=["probe", "render_frame", "export"], help="Video action"
    )
    vid_cmd.add_argument(
        "--input", dest="input_path", default=None, help="Standalone media clip path"
    )
    vid_cmd.add_argument(
        "--project", dest="project_path", default=None, help="FilmCraft project (.fcproj) path"
    )
    vid_cmd.add_argument(
        "--demo", action="store_true", default=False, help="Use built-in demo project"
    )
    vid_cmd.add_argument(
        "-o", "--output", dest="output_path", default=None, help="Output file path"
    )
    vid_cmd.add_argument(
        "--seconds", type=float, default=0.0, help="Timestamp in seconds for render_frame"
    )
    vid_cmd.add_argument(
        "--start", dest="start_seconds", type=float, default=None, help="Custom range start (s)"
    )
    vid_cmd.add_argument(
        "--end", dest="end_seconds", type=float, default=None, help="Custom range end (s)"
    )
    vid_cmd.add_argument("--format", default=None, help="Export format override")
    vid_cmd.add_argument("--preset", default=None, help="Export preset name")
    vid_cmd.add_argument("--scale", type=float, default=None, help="Frame scale factor (e.g. 0.5)")
    vid_cmd.add_argument("--quality", type=int, default=None, help="Export quality 0..100")
    vid_cmd.add_argument(
        "--no-audio", action="store_true", default=False, help="Omit audio streams"
    )
    vid_cmd.add_argument(
        "--allow-overwrite",
        action="store_true",
        default=False,
        help="Allow overwriting existing output",
    )
    vid_cmd.set_defaults(func=_cmd_video)

    # Portable recipe workflows (list/init/validate/export/import/run)
    rec_cmd = sub.add_parser(
        "recipe", help="List, create, validate, trade, and replay portable recipes"
    )
    rec_sub = rec_cmd.add_subparsers(dest="recipe_action", required=True)

    r_list = rec_sub.add_parser("list", help="List installed and bundled recipes")
    r_list.add_argument("--skills-dir", default=None, help="User skills/recipes directory")
    r_list.set_defaults(func=_cmd_recipe)

    r_init = rec_sub.add_parser("init", help="Scaffold a new portable recipe directory")
    r_init.add_argument("slug", help="Recipe slug (e.g. 'amber-film' -> 'recipe-amber-film')")
    r_init.add_argument(
        "--app",
        choices=["photocraft", "lightcraft", "soundcraft", "filmcraft"],
        default="lightcraft",
        help="Target ArtCraft app (default: lightcraft)",
    )
    r_init.add_argument("--dest-dir", default=None, help="Destination skills directory")
    r_init.add_argument("--author", default="wspotter", help="Author identifier")
    r_init.add_argument("--description", default=None, help="<=60 char description ending with '.'")
    r_init.add_argument("--allow-overwrite", action="store_true", default=False)
    r_init.set_defaults(func=_cmd_recipe)

    r_val = rec_sub.add_parser("validate", help="Validate a recipe SKILL.md and recipe.json")
    r_val.add_argument("recipe", help="Recipe name/slug or directory path")
    r_val.add_argument("--skills-dir", default=None, help="User skills/recipes directory")
    r_val.add_argument("--allow-doc-only", action="store_true", default=False)
    r_val.set_defaults(func=_cmd_recipe)

    r_exp = rec_sub.add_parser("export", help="Pack a validated recipe into a portable zip")
    r_exp.add_argument("recipe", help="Recipe name/slug or directory path")
    r_exp.add_argument("archive_path", help="Destination .zip archive path")
    r_exp.add_argument("--skills-dir", default=None, help="User skills/recipes directory")
    r_exp.add_argument("--allow-overwrite", action="store_true", default=False)
    r_exp.set_defaults(func=_cmd_recipe)

    r_imp = rec_sub.add_parser("import", help="Verify and install a traded recipe zip bundle")
    r_imp.add_argument("archive_path", help="Path to traded .zip archive")
    r_imp.add_argument("--dest-dir", default=None, help="Destination skills directory")
    r_imp.add_argument("--allow-overwrite", action="store_true", default=False)
    r_imp.set_defaults(func=_cmd_recipe)

    r_run = rec_sub.add_parser("run", help="Replay a validated multi-step recipe non-destructively")
    r_run.add_argument("recipe", help="Recipe name/slug or directory path")
    r_run.add_argument("input_path", help="Original source media path (never modified)")
    r_run.add_argument("output_path", help="New destination output path")
    r_run.add_argument(
        "--param",
        action="append",
        default=[],
        help="Override recipe parameter (key=value, repeatable)",
    )
    r_run.add_argument("--params-json", default=None, help="JSON object of parameter overrides")
    r_run.add_argument(
        "--work-dir", default=None, help="Working directory for intermediate artifacts"
    )
    r_run.add_argument("--skills-dir", default=None, help="User skills/recipes directory")
    r_run.add_argument("--dry-run", action="store_true", default=False)
    r_run.add_argument("--allow-overwrite", action="store_true", default=False)
    r_run.set_defaults(func=_cmd_recipe)


def main(argv: Any = None) -> int:
    """Standalone CLI entrypoint (`python -m artcraft_plugin.cli`)."""
    parser = argparse.ArgumentParser(prog="artcraft-plugin")
    register_cli(parser)
    parsed = parser.parse_args(argv)
    return int(parsed.func(parsed))


if __name__ == "__main__":
    sys.exit(main())
