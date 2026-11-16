"""Tests for tool handlers, runner guards, and Hermes register(ctx) wiring."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

spec = importlib.util.spec_from_file_location(
    "test_artcraft_plugin",
    Path(__file__).resolve().parents[1] / "__init__.py",
    submodule_search_locations=[str(Path(__file__).resolve().parents[1])],
)
plugin_root = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin_root
spec.loader.exec_module(plugin_root)
from artcraft_plugin import schemas, tools  # noqa: E402


class _FakeCtx:
    def __init__(self) -> None:
        self.tools = {}
        self.cli_commands = {}
        self.skills = {}

    def register_tool(self, *, name: str, toolset: str, schema: dict, handler) -> None:
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_cli_command(self, name: str, help: str, setup_fn, description: str = "") -> None:
        self.cli_commands[name] = {"register_fn": setup_fn, "description": description}

    def register_skill(self, name: str, path: Path) -> None:
        self.skills[name] = path


class TestToolsAndPluginRegistration(unittest.TestCase):
    def test_register_wires_all_tools_and_cli(self) -> None:
        ctx = _FakeCtx()
        plugin_root.register(ctx)
        self.assertEqual(
            set(ctx.tools.keys()),
            {
                "artcraft_status",
                "artcraft_inspect",
                "artcraft_prepare_inspection",
                "artcraft_prepare_print",
                "artcraft_verify_edit",
                "photocraft_run",
                "photocraft_spot_heal",
                "lightcraft_run",
                "artcraft_restore_step",
                "artcraft_checkpoint",
                "artcraft_build_review",
                "artcraft_job",
                "artcraft_develop",
                "artcraft_audio_basic",
                "artcraft_video_basic",
                "artcraft_recipe",
            },
        )
        self.assertEqual(len(ctx.tools), 16)
        for tool in ctx.tools.values():
            self.assertEqual(tool["toolset"], "artcraft")
        self.assertIn("artcraft", ctx.cli_commands)
        self.assertEqual(len(ctx.skills), 19)
        self.assertIn("recipe-maker", ctx.skills)
        self.assertIn("recipe-film-matte", ctx.skills)
        self.assertIn("recipe-voice-master", ctx.skills)
        self.assertIn("recipe-web-clip", ctx.skills)
        self.assertIn("artcraft-router", ctx.skills)
        for skill_path in ctx.skills.values():
            self.assertTrue(skill_path.is_file())

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
                (
                    "output_parent_nonexistent",
                    {**base_args, "output_path": str(root / "no_dir" / "out.png")},
                ),
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

    def test_prepare_inspection_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "photo.png"
            Image.new("RGB", (64, 48), color=(200, 100, 50)).save(src)
            work = root / "inspect_work"

            # Missing path
            err_res = json.loads(tools.artcraft_prepare_inspection({}))
            self.assertFalse(err_res["ok"])

            # Valid inspection
            res = json.loads(
                tools.artcraft_prepare_inspection(
                    {"path": str(src), "working_dir": str(work), "crop_size": 32}
                )
            )
            self.assertTrue(res["ok"])
            self.assertTrue(res["valid"])
            self.assertEqual(res["source"]["orientation"], "landscape")
            self.assertIn("inspection_artifacts", res)
            self.assertTrue(Path(res["inspection_artifacts"]["whole_photo_preview"]["path"]).exists())
            self.assertGreaterEqual(len(res["inspection_artifacts"]["native_resolution_crops"]), 1)
            self.assertIn("measured_clues", res)
            self.assertIn("measurement_limits", res["measured_clues"])

    def test_prepare_print_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "input.png"
            out = root / "output.png"
            # 800x1000 has 4:5 aspect ratio, matching 8x10
            Image.new("RGB", (800, 1000), color=(100, 150, 200)).save(src)

            # Missing required inputs
            missing_res = json.loads(tools.artcraft_prepare_print({}))
            self.assertFalse(missing_res["ok"])
            self.assertIn("Missing required", missing_res["error"])

            # Valid matching call
            res = json.loads(
                tools.artcraft_prepare_print(
                    {
                        "input_path": str(src),
                        "output_path": str(out),
                        "width_in": 8.0,
                        "height_in": 10.0,
                        "ppi": 100,
                    }
                )
            )
            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "prepared")
            self.assertEqual(res["delivery_file"]["width_px"], 800)
            self.assertEqual(res["delivery_file"]["height_px"], 1000)
            self.assertTrue(out.exists())

    def test_restore_step_and_checkpoint_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            src = root / "input.png"
            out = root / "out_restored.png"
            cp_dir = root / "checkpoints"
            Image.new("RGB", (200, 200), color=(110, 110, 110)).save(src)

            # Test missing arguments
            missing_res = json.loads(tools.artcraft_restore_step({}))
            self.assertFalse(missing_res["ok"])

            # Confirmation gate should stop without writing output
            gate_res = json.loads(
                tools.artcraft_restore_step(
                    {
                        "input_path": str(src),
                        "output_path": str(out),
                        "recipe": "faded_tones",
                        "reconstruct_missing": True,
                        "checkpoint_dir": str(cp_dir),
                    }
                )
            )
            self.assertFalse(gate_res["ok"])
            self.assertEqual(gate_res["status"], "needs_decision")
            self.assertTrue(gate_res["original_intact"])
            self.assertFalse(out.exists())

            # Test checkpoint tool list empty
            list_res = json.loads(
                tools.artcraft_checkpoint({"action": "list", "checkpoint_dir": str(cp_dir)})
            )
            self.assertTrue(list_res["ok"])
            self.assertEqual(list_res["checkpoints"], [])

    def test_artcraft_status_reports_standalone_and_cli_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as empty_dir, patch(
            "artcraft_plugin.discovery._candidate_dirs", return_value=[Path(empty_dir)]
        ), patch("artcraft_plugin.discovery.shutil.which", return_value=None):
            res = json.loads(tools.artcraft_status({}))
            self.assertTrue(res["ok"])
            self.assertIn("apps", res)
            caps = res["capabilities"]
            self.assertTrue(caps["pillow_available"])
            self.assertIn("artcraft_prepare_print", caps["available_tools"])
            self.assertIn("artcraft_build_review", caps["available_tools"])
            self.assertNotIn("photocraft_spot_heal", caps["available_tools"])
            self.assertNotIn("artcraft_restore_step", caps["available_tools"])
            self.assertIn("photocraft_spot_heal", caps["unavailable_tools"])
            self.assertIn("artcraft_restore_step", caps["unavailable_tools"])
            self.assertIn("artcraft_develop", caps["unavailable_tools"])
            restore_caps = caps["partial_tools"]["artcraft_restore_step"]
            self.assertFalse(restore_caps["available"])
            self.assertEqual(restore_caps["standalone_recipes"], [])
            self.assertIn("noise_and_grain", restore_caps["cli_recipes"])
            self.assertFalse(restore_caps["cli_recipes"]["dust_and_scratches"]["available"])

    def test_tool_schema_and_validation_guards(self) -> None:
        print_props = schemas.ARTCRAFT_PREPARE_PRINT["parameters"]["properties"]
        self.assertIn("allow_overwrite", print_props)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "in.png"
            out = root / "out.png"
            Image.new("RGB", (80, 100), color=(40, 80, 120)).save(src)
            Image.new("RGB", (80, 100), color=(10, 10, 10)).save(out)

            bad_ppi = json.loads(
                tools.artcraft_prepare_print(
                    {
                        "input_path": str(src),
                        "output_path": str(root / "fresh.png"),
                        "width_in": 8.0,
                        "height_in": 10.0,
                        "ppi": 0,
                    }
                )
            )
            self.assertFalse(bad_ppi["ok"])

            refused = json.loads(
                tools.artcraft_prepare_print(
                    {
                        "input_path": str(src),
                        "output_path": str(out),
                        "width_in": 8.0,
                        "height_in": 10.0,
                        "ppi": 10,
                    }
                )
            )
            self.assertFalse(refused["ok"])

            allowed = json.loads(
                tools.artcraft_prepare_print(
                    {
                        "input_path": str(src),
                        "output_path": str(out),
                        "width_in": 8.0,
                        "height_in": 10.0,
                        "ppi": 10,
                        "allow_overwrite": True,
                    }
                )
            )
            self.assertTrue(allowed["ok"], allowed)

            blank_recipe = json.loads(
                tools.artcraft_restore_step(
                    {
                        "input_path": str(src),
                        "output_path": str(root / "r.png"),
                        "recipe": "   ",
                    }
                )
            )
            self.assertFalse(blank_recipe["ok"])

            bad_timeout = json.loads(
                tools.photocraft_spot_heal(
                    {
                        "input_path": str(src),
                        "output_path": str(root / "h.png"),
                        "points": [[10, 10]],
                        "size": 4,
                        "region": [5, 5, 20, 20],
                        "timeout_s": -5,
                    }
                )
            )
            self.assertFalse(bad_timeout["ok"])

