"""CLI subcommands registered under `hermes artcraft`."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .discovery import discover_all
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


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Wire `doctor` and `verify` subcommands onto a parent argparse subparser."""
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


def main(argv: Any = None) -> int:
    """Standalone CLI entrypoint (`python -m artcraft_plugin.cli`)."""
    parser = argparse.ArgumentParser(prog="artcraft-plugin")
    register_cli(parser)
    parsed = parser.parse_args(argv)
    return int(parsed.func(parsed))


if __name__ == "__main__":
    sys.exit(main())
