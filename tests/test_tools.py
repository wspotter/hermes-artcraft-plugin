"""Tests for tool handlers, runner guards, and Hermes register(ctx) wiring."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import __init__ as plugin_root
from artcraft_plugin import tools


class _FakeCtx:
    def __init__(self) -> None:
        self.tools = {}
        self.cli_commands = {}

    def register_tool(self, *, name: str, toolset: str, schema: dict, handler) -> None:
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_cli_command(self, name: str, register_fn, description: str = "") -> None:
        self.cli_commands[name] = {"register_fn": register_fn, "description": description}


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
                "lightcraft_run",
            },
        )
        for tool in ctx.tools.values():
            self.assertEqual(tool["toolset"], "artcraft")
        self.assertIn("artcraft", ctx.cli_commands)

    def test_non_destructive_guard_blocks_same_input_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake_cli = bin_dir / "photocraft-cli"
            fake_cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_cli.chmod(fake_cli.stat().st_mode | stat.S_IEXEC)

            img = Path(tmp) / "photo.png"
            Image.new("RGB", (16, 16), (10, 20, 30)).save(img)

            with patch.dict(os.environ, {"ARTCRAFT_BIN_DIR": str(bin_dir)}):
                raw = tools.photocraft_run(
                    {
                        "cli_args": ["heal", str(img), str(img)],
                        "input_path": str(img),
                        "output_path": str(img),
                    }
                )
            data = json.loads(raw)
            self.assertFalse(data["ok"])
            self.assertIn("non_destructive_guard", data["error"])

    def test_photocraft_run_catches_noop_and_passes_real_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            src = Path(tmp) / "in.png"
            out_noop = Path(tmp) / "out_noop.png"
            out_ok = Path(tmp) / "out_ok.png"
            Image.new("RGB", (16, 16), (255, 255, 255)).save(src)

            # Fake CLI that either copies input (no-op) or flips one pixel depending on arg[0]
            fake_cli = bin_dir / "photocraft-cli"
            fake_cli.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "from PIL import Image\n"
                "mode, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]\n"
                "img = Image.open(src)\n"
                "if mode == 'edit':\n"
                "    img.putpixel((2, 2), (0, 0, 0))\n"
                "img.save(dst)\n",
                encoding="utf-8",
            )
            fake_cli.chmod(fake_cli.stat().st_mode | stat.S_IEXEC)

            with patch.dict(os.environ, {"ARTCRAFT_BIN_DIR": str(bin_dir)}):
                noop_res = json.loads(
                    tools.photocraft_run(
                        {
                            "cli_args": ["noop", str(src), str(out_noop)],
                            "input_path": str(src),
                            "output_path": str(out_noop),
                        }
                    )
                )
                self.assertFalse(noop_res["ok"])
                self.assertIn("no_op_edit", noop_res["error"])

                ok_res = json.loads(
                    tools.photocraft_run(
                        {
                            "cli_args": ["edit", str(src), str(out_ok)],
                            "input_path": str(src),
                            "output_path": str(out_ok),
                            "region": [0, 0, 5, 5],
                        }
                    )
                )
                self.assertTrue(ok_res["ok"])
                self.assertTrue(ok_res["verification"]["passed"])
                self.assertEqual(ok_res["verification"]["pixel_diff"]["changed_pixels"], 1)


if __name__ == "__main__":
    unittest.main()
