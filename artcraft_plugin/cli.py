"""CLI subcommands registered under `hermes artcraft`."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .discovery import discover_all
from .inspect import prepare_inspection
from .print_prep import prepare_print
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



def main(argv: Any = None) -> int:
    """Standalone CLI entrypoint (`python -m artcraft_plugin.cli`)."""
    parser = argparse.ArgumentParser(prog="artcraft-plugin")
    register_cli(parser)
    parsed = parser.parse_args(argv)
    return int(parsed.func(parsed))


if __name__ == "__main__":
    sys.exit(main())
