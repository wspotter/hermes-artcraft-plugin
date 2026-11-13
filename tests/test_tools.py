"""Tests for tool handlers, runner guards, and Hermes register(ctx) wiring."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import importlib.util

spec = importlib.util.spec_from_file_location(
    "test_artcraft_plugin", Path(__file__).resolve().parents[1] / "__init__.py",
    submodule_search_locations=[str(Path(__file__).resolve().parents[1])],
)
plugin_root = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin_root
spec.loader.exec_module(plugin_root)
from artcraft_plugin import tools


class _FakeCtx:
    def __init__(self) -> None:
        self.tools = {}
        self.cli_commands = {}

    def register_tool(self, *, name: str, toolset: str, schema: dict, handler) -> None:
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_cli_command(self, name: str, help: str, setup_fn, description: str = "") -> None:
        self.cli_commands[name] = {"register_fn": setup_fn, "description": description}


class TestToolsAndPluginRegistration(unittest.TestCase):
    def test_register_wires_all_tools_and_cli(self) -> None:
        ctx = _FakeCtx()
        plugin_root.register(ctx)
        self.assertEqual(
            set(ctx.tools.keys()),
            {
                "artcraft_status",
                "artcraft_inspect",
                "artcraft_verify_edit",
                "photocraft_run",
                "photocraft_spot_heal",
                "lightcraft_run",
            },
        )
        for tool in ctx.tools.values():
            self.assertEqual(tool["toolset"], "artcraft")
        self.assertIn("artcraft", ctx.cli_commands)

    def test_raw_edit_arguments_are_rejected(self) -> None:
        self.assertFalse(json.loads(tools.photocraft_run({"cli_args": ["run"]}))["ok"])

    def test_spot_heal_only_publishes_verified_new_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, out = root / "in.png", root / "out.png"
            Image.new("RGB", (16, 16), "white").save(src)
            original = src.read_bytes()
            binary = root / "photocraft-cli"
            binary.touch()
            binary.chmod(0o700)
            args = dict(input_path=str(src), output_path=str(out),
                        points=[[2, 2]], size=2, region=[0, 0, 5, 5])
            with patch.dict(os.environ, {"ARTCRAFT_BIN_DIR": str(root)}):
                binary.write_text("#!/bin/sh\nexit 0\n")
                self.assertFalse(json.loads(tools.photocraft_spot_heal(args))["ok"])
                self.assertFalse(out.exists())

                for coordinates, passed in [((10, 10), False), ((2, 2), True)]:
                    binary.write_text(
                        f"#!{sys.executable}\n"
                        "import sys\nfrom PIL import Image\n"
                        "img = Image.open(sys.argv[2])\n"
                        f"img.putpixel({coordinates}, (0, 0, 0))\n"
                        "img.save(sys.argv[-1])\n"
                    )
                    result = json.loads(tools.photocraft_spot_heal(args))
                    self.assertEqual(result["ok"], passed, result)
                    self.assertEqual(out.exists(), passed)
                before = out.read_bytes()
                self.assertFalse(json.loads(tools.photocraft_spot_heal(args))["ok"])
                self.assertEqual(out.read_bytes(), before)
                self.assertEqual(src.read_bytes(), original)

    def test_spot_heal_missing_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out.png"
            res = json.loads(
                tools.photocraft_spot_heal(
                    {
                        "input_path": str(root / "nonexistent.png"),
                        "output_path": str(out),
                        "points": [[2, 2]],
                        "size": 2,
                        "region": [0, 0, 5, 5],
                    }
                )
            )
            self.assertFalse(res["ok"])
            self.assertFalse(out.exists())

    def test_spot_heal_invalid_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "in.png"
            out = root / "out.png"
            Image.new("RGB", (16, 16), "white").save(src)
            src_bytes = src.read_bytes()

            base_args = {
                "input_path": str(src),
                "output_path": str(out),
                "points": [[2, 2]],
                "size": 2,
                "region": [0, 0, 5, 5],
            }

            invalid_cases = [
                ("size_too_small", {**base_args, "size": 0}),
                ("size_too_large", {**base_args, "size": 257}),
                ("size_not_int", {**base_args, "size": "big"}),
                ("region_too_short", {**base_args, "region": [0, 0, 5]}),
                ("region_negative_dim", {**base_args, "region": [0, 0, -5, 5]}),
                ("region_out_of_bounds", {**base_args, "region": [0, 0, 20, 20]}),
                ("points_empty", {**base_args, "points": []}),
                ("points_outside_region", {**base_args, "points": [[10, 10]]}),
                ("output_not_png", {**base_args, "output_path": str(root / "out.jpg")}),
                ("output_parent_nonexistent", {**base_args, "output_path": str(root / "no_dir" / "out.png")}),
            ]

            for label, args in invalid_cases:
                with self.subTest(case=label):
                    res = json.loads(tools.photocraft_spot_heal(args))
                    self.assertFalse(res["ok"], f"Expected failure for {label}: {res}")
                    self.assertFalse(out.exists(), f"Output must not exist for {label}")
                    self.assertEqual(src.read_bytes(), src_bytes)

    def test_spot_heal_existing_output_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, out = root / "in.png", root / "out.png"
            Image.new("RGB", (16, 16), "white").save(src)
            Image.new("RGB", (16, 16), "blue").save(out)
            src_bytes = src.read_bytes()
            out_bytes = out.read_bytes()

            res = json.loads(
                tools.photocraft_spot_heal(
                    {
                        "input_path": str(src),
                        "output_path": str(out),
                        "points": [[2, 2]],
                        "size": 2,
                        "region": [0, 0, 5, 5],
                    }
                )
            )
            self.assertFalse(res["ok"])
            self.assertIn("must name a new PNG", res["error"])
            self.assertEqual(out.read_bytes(), out_bytes)
            self.assertEqual(src.read_bytes(), src_bytes)

    def test_spot_heal_timeout_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, out = root / "in.png", root / "out.png"
            Image.new("RGB", (16, 16), "white").save(src)
            src_bytes = src.read_bytes()

            binary = root / "photocraft-cli"
            binary.write_text("#!/bin/sh\nsleep 5\n")
            binary.chmod(0o700)

            args = {
                "input_path": str(src),
                "output_path": str(out),
                "points": [[2, 2]],
                "size": 2,
                "region": [0, 0, 5, 5],
                "timeout_s": 0.2,
            }
            with patch.dict(os.environ, {"ARTCRAFT_BIN_DIR": str(root)}):
                res = json.loads(tools.photocraft_spot_heal(args))
                self.assertFalse(res["ok"])
                self.assertIn("timeout", res["error"])
                self.assertFalse(out.exists())
                self.assertEqual(src.read_bytes(), src_bytes)
