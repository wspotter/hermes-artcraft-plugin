"""CLI subcommands registered under `hermes artcraft`."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .discovery import discover_all
from .inspect import prepare_inspection
from .jobs import (
    get_job,
    init_job,
    record_delivery,
    record_export_artifact,
    reconcile_delivery,
    resume_job,
    save_checkpoint,
)
from .print_prep import prepare_print
from .restore import get_checkpoint, list_checkpoints, restore_step
from .review import build_review_package
from .verify import verify_edit


def _cmd_doctor(_args: argparse.Namespace) -> int:
    discovered = discover_all()
    print(json.dumps({k: v.to_dict() for k, v in discovered.items()}, indent=2))
    return 0 if any(info.available for info in discovered.values()) else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify_edit(
        args.input_path,
        args.output_path,
        expected_width=args.width,
        expected_height=args.height,
        region=args.region,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("passed") else 1


def _cmd_inspect(args: argparse.Namespace) -> int:
    result = prepare_inspection(
        args.path,
        working_dir=args.working_dir,
        max_preview_dimension=args.preview_max,
        crop_size=args.crop_size,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("valid") else 1


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
            return 2  # Special exit code for stop/ask gate
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
            res = init_job(job_id=job_id, source_path=getattr(args, "source", None), workspace_dir=workspace_dir, metadata=meta)
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



def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Wire `doctor`, `verify`, and `inspect` subcommands onto a parent argparse subparser."""
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

    inspect_cmd = sub.add_parser("inspect", help="Prepare preview, crops, and measured clues for visual inspection")
    inspect_cmd.add_argument("path", help="Path to source image")
    inspect_cmd.add_argument("--working-dir", default=None, help="Directory to save preview and crops")
    inspect_cmd.add_argument("--preview-max", type=int, default=1024, help="Maximum preview dimension (default 1024)")
    inspect_cmd.add_argument("--crop-size", type=int, default=256, help="Pixel size for native crops (default 256)")
    inspect_cmd.set_defaults(func=_cmd_inspect)

    prep_cmd = sub.add_parser("prep-print", help="Prepare a verified print delivery file")
    prep_cmd.add_argument("input_path", help="Path to source image")
    prep_cmd.add_argument("output_path", help="Path to destination print file")
    prep_cmd.add_argument("--width", type=float, required=True, dest="width_in", help="Target print width in inches")
    prep_cmd.add_argument("--height", type=float, required=True, dest="height_in", help="Target print height in inches")
    prep_cmd.add_argument("--orientation", choices=["auto", "portrait", "landscape"], default="auto", help="Print orientation (default auto)")
    prep_cmd.add_argument("--fit-mode", choices=["auto", "borderless", "crop", "margins", "fit"], default="auto", help="Fit mode (default auto)")
    prep_cmd.add_argument("--confirm-crop", action="store_true", default=False, help="Confirm cropping if aspect ratio conflicts")
    prep_cmd.add_argument("--ppi", type=int, default=300, help="Target export PPI (default 300)")
    prep_cmd.add_argument("--format", dest="output_format", choices=["auto", "PNG", "TIFF", "JPEG"], default="auto", help="Output format (default auto)")
    prep_cmd.add_argument("--margin-color", default="white", help="Margin color for fit mode (default white)")
    prep_cmd.add_argument("--preserve-master", dest="preserve_master_path", default=None, help="Path to preserve master copy")
    prep_cmd.add_argument("--allow-upscale", action="store_true", default=False, help="Allow upscaling small images")
    prep_cmd.add_argument("--target-icc", default=None, help="Target ICC profile path or 'sRGB'")
    prep_cmd.add_argument("--preview-path", default=None, help="Explicit path for preview image")
    prep_cmd.set_defaults(func=_cmd_prep_print)

    restore_cmd = sub.add_parser("restore", help="Apply a restoration recipe with checkpointing and crops")
    restore_cmd.add_argument("recipe", choices=["faded_tones", "color_cast", "dust_and_scratches", "noise_and_grain", "sharpening", "enlargement"], help="Restoration recipe")
    restore_cmd.add_argument("input_path", help="Path to input photo")
    restore_cmd.add_argument("output_path", help="Path to output photo")
    restore_cmd.add_argument("--params", default=None, help="JSON-encoded recipe parameters")
    restore_cmd.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "W", "H"), default=None, help="Optional [x y w h] region")
    restore_cmd.add_argument("--checkpoint-dir", default=None, help="Checkpoint directory")
    restore_cmd.add_argument("--step-name", default=None, help="Custom step name")
    restore_cmd.add_argument("--ppi", type=int, default=300, help="Target print resolution PPI (default 300)")
    restore_cmd.add_argument("--reconstruct-missing", action="store_true", default=False, help="Reconstruct missing features (Stop/Ask gate)")
    restore_cmd.add_argument("--content-type", default=None, help="Content type hint (e.g. missing_face)")
    restore_cmd.add_argument("--allow-overwrite", action="store_true", default=False, help="Allow overwriting output")
    restore_cmd.set_defaults(func=_cmd_restore)

    cp_cmd = sub.add_parser("checkpoint", help="Manage restoration checkpoints")
    cp_cmd.add_argument("action", choices=["list", "get"], help="Checkpoint action")
    cp_cmd.add_argument("checkpoint_dir", help="Path to checkpoint directory")
    cp_cmd.add_argument("--step-id", default=None, help="Step index or name for get action")
    cp_cmd.set_defaults(func=_cmd_checkpoint)

    # Phase 5: Review Package & Quality Traps
    rev_cmd = sub.add_parser("review", help="Build review package and test for defect traps")
    rev_cmd.add_argument("source_path", help="Path to original source photo")
    rev_cmd.add_argument("output_path", help="Path to edited output photo")
    rev_cmd.add_argument("--working-dir", default=None, help="Directory to save previews and crops")
    rev_cmd.add_argument("--region", type=int, nargs=4, metavar=("X", "Y", "W", "H"), default=None, help="Target repair region [x y w h]")
    rev_cmd.add_argument("--regions", default=None, help="JSON-encoded list of repair regions [[x,y,w,h], ...]")
    rev_cmd.add_argument("--preview-max", type=int, default=1024, help="Max preview dimension in pixels (default 1024)")
    rev_cmd.add_argument("--crop-size", type=int, default=256, help="Native crop dimension in pixels (default 256)")
    rev_cmd.add_argument("--crop-geometry", type=json.loads, help="JSON crop rect or quad in source pixels")
    rev_cmd.add_argument("--expected-aspect", default=None, help="Optional expected aspect ratio (e.g. '4:5' or 0.8)")
    rev_cmd.add_argument("--no-preserve-framing", action="store_false", dest="preserve_framing", default=True, help="Allow aspect/framing shift from source")
    rev_cmd.add_argument("--retry-count", type=int, default=0, help="Current retry count")
    rev_cmd.add_argument("--max-retries", type=int, default=3, help="Max retry limit")
    rev_cmd.add_argument("--last-checkpoint", default=None, help="Path to last verified checkpoint")
    rev_cmd.set_defaults(func=_cmd_review)

    # Phase 6: Job Workspaces, Checkpoints & Delivery Receipts
    job_cmd = sub.add_parser("job", help="Manage deterministic job workspaces and delivery receipts")
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
    j_cp.add_argument("--not-verified", action="store_true", default=False, help="Mark checkpoint unverified")
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
    j_export.add_argument("--not-verified", action="store_true", default=False, help="Mark artifact unverified")
    j_export.add_argument("--workspace", default=None, help="Base workspace directory")
    j_export.add_argument("--meta", default=None, help="JSON-encoded metadata")
    j_export.set_defaults(func=_cmd_job)

    j_deliver = job_sub.add_parser("deliver", help="Record delivery receipt")
    j_deliver.add_argument("job_id", help="Unique job ID")
    j_deliver.add_argument("--artifact-id", required=True, help="Export artifact ID to deliver")
    j_deliver.add_argument("--destination", required=True, help="Destination path or URI")
    j_deliver.add_argument("--status", choices=["pending", "delivered", "uncertain"], default="pending", help="Delivery status")
    j_deliver.add_argument("--receipt-id", default=None, help="Optional receipt ID")
    j_deliver.add_argument("--workspace", default=None, help="Base workspace directory")
    j_deliver.add_argument("--notes", default=None, help="Notes or delivery reason")
    j_deliver.set_defaults(func=_cmd_job)

    j_recon = job_sub.add_parser("reconcile", help="Reconcile uncertain delivery")
    j_recon.add_argument("job_id", help="Unique job ID")
    j_recon.add_argument("--destination", required=True, help="Destination path or URI")
    j_recon.add_argument("--receipt-id", default=None, help="Receipt ID to reconcile")
    j_recon.add_argument("--status", choices=["delivered", "failed"], default=None, help="Explicit confirmation status")
    j_recon.add_argument("--workspace", default=None, help="Base workspace directory")
    j_recon.add_argument("--notes", default=None, help="Reconciliation notes")
    j_recon.set_defaults(func=_cmd_job)

    j_status = job_sub.add_parser("status", help="Get job status")
    j_status.add_argument("job_id", help="Unique job ID")
    j_status.add_argument("--workspace", default=None, help="Base workspace directory")
    j_status.set_defaults(func=_cmd_job)



def main(argv: Any = None) -> int:
    """Standalone CLI entrypoint (`python -m artcraft_plugin.cli`)."""
    parser = argparse.ArgumentParser(prog="artcraft-plugin")
    register_cli(parser)
    parsed = parser.parse_args(argv)
    return int(parsed.func(parsed))


if __name__ == "__main__":
    sys.exit(main())
