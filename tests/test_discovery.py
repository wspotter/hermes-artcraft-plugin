"""Tests for ArtCraft CLI binary discovery."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from artcraft_plugin.discovery import (
    BinaryInfo,
    discover_all,
    find_cli_binary,
    status_payload,
    summarize_capabilities,
)


class TestDiscovery(unittest.TestCase):
    def test_prefers_cli_binary_in_artcraft_bin_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            cli_bin = bin_dir / "photocraft-cli"
            gui_bin = bin_dir / "photocraft"
            cli_bin.write_text("#!/bin/sh\necho 'photocraft-cli 0.23.1'\n", encoding="utf-8")
            gui_bin.write_text("#!/bin/sh\necho 'photocraft 0.23.1'\n", encoding="utf-8")
            cli_bin.chmod(cli_bin.stat().st_mode | stat.S_IEXEC)
            gui_bin.chmod(gui_bin.stat().st_mode | stat.S_IEXEC)

            with patch.dict(os.environ, {"ARTCRAFT_BIN_DIR": str(bin_dir)}):
                with patch("artcraft_plugin.discovery.shutil.which", return_value=None):
                    found = find_cli_binary("photocraft")
                    self.assertEqual(found, cli_bin)

    def test_unknown_app_raises(self) -> None:
        with self.assertRaises(ValueError):
            find_cli_binary("unknowncraft")

    def test_discovers_from_hermes_home_bin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home_dir = Path(tmp)
            bin_dir = home_dir / "bin"
            bin_dir.mkdir()
            cli_bin = bin_dir / "photocraft-cli"
            cli_bin.write_text("#!/bin/sh\necho 'photocraft-cli 0.23.1'\n", encoding="utf-8")
            cli_bin.chmod(cli_bin.stat().st_mode | stat.S_IEXEC)

            with patch.dict(os.environ, {"HERMES_HOME": str(home_dir), "ARTCRAFT_BIN_DIR": ""}):
                with patch("artcraft_plugin.discovery.shutil.which", return_value=None):
                    found = find_cli_binary("photocraft")
                    self.assertEqual(found, cli_bin)

    def test_discovers_from_hermes_profile_bin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp)
            profile_bin = fake_home / ".hermes" / "profiles" / "testprofile" / "bin"
            profile_bin.mkdir(parents=True)
            cli_bin = profile_bin / "lightcraft-cli"
            cli_bin.write_text("#!/bin/sh\necho 'lightcraft-cli 0.21.1'\n", encoding="utf-8")
            cli_bin.chmod(cli_bin.stat().st_mode | stat.S_IEXEC)

            with patch.object(Path, "home", return_value=fake_home):
                env = {"HERMES_PROFILE": "testprofile", "HERMES_HOME": "", "ARTCRAFT_BIN_DIR": ""}
                with patch.dict(os.environ, env):
                    with patch("artcraft_plugin.discovery.shutil.which", return_value=None):
                        found = find_cli_binary("lightcraft")
                        self.assertEqual(found, cli_bin)

    def test_discovers_from_any_hermes_profile_bin_glob(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp)
            profile_bin = fake_home / ".hermes" / "profiles" / "custom_agent" / "bin"
            profile_bin.mkdir(parents=True)
            cli_bin = profile_bin / "soundcraft-cli"
            cli_bin.write_text("#!/bin/sh\necho 'soundcraft-cli 0.20.1'\n", encoding="utf-8")
            cli_bin.chmod(cli_bin.stat().st_mode | stat.S_IEXEC)

            with patch.object(Path, "home", return_value=fake_home):
                env = {"HERMES_PROFILE": "", "HERMES_HOME": "", "ARTCRAFT_BIN_DIR": ""}
                with patch.dict(os.environ, env):
                    with patch("artcraft_plugin.discovery.shutil.which", return_value=None):
                        found = find_cli_binary("soundcraft")
                        self.assertEqual(found, cli_bin)

    def test_discover_all_reports_missing_cleanly(self) -> None:
        with patch("artcraft_plugin.discovery.find_cli_binary", return_value=None):
            res = discover_all()
            expected_apps = {"photocraft", "lightcraft", "filmcraft", "soundcraft"}
            self.assertEqual(set(res.keys()), expected_apps)
            for info in res.values():
                self.assertFalse(info.available)
                self.assertIsNone(info.path)

    def test_capabilities_when_photocraft_absent_marks_restore_step_unavailable(self) -> None:
        discovered = {
            app: BinaryInfo(
                app=app, binary_name=f"{app}-cli", path=None, version=None, available=False
            )
            for app in ("photocraft", "lightcraft", "filmcraft", "soundcraft")
        }
        caps = summarize_capabilities(discovered, pillow_available=True)

        self.assertNotIn("artcraft_restore_step", caps["available_tools"])
        self.assertEqual(
            caps["unavailable_tools"].get("artcraft_restore_step"),
            "Requires photocraft-cli (not found)",
        )
        self.assertIn("artcraft_restore_step", caps["cli_tools"]["photocraft"]["tools"])
        self.assertFalse(caps["cli_tools"]["photocraft"]["available"])

        restore_meta = caps["partial_tools"]["artcraft_restore_step"]
        self.assertFalse(restore_meta["available"])
        self.assertEqual(restore_meta["standalone_recipes"], [])
        expected_recipes = {
            "faded_tones",
            "color_cast",
            "dust_and_scratches",
            "noise_and_grain",
            "sharpening",
            "enlargement",
        }
        self.assertEqual(set(restore_meta["cli_recipes"].keys()), expected_recipes)
        self.assertNotIn("noise_grain", restore_meta["cli_recipes"])
        for meta in restore_meta["cli_recipes"].values():
            self.assertEqual(meta["requires_app"], "photocraft")
            self.assertFalse(meta["available"])

    def test_status_payload_and_capabilities_when_photocraft_present(self) -> None:
        with tempfile.TemporaryDirectory() as empty_dir, patch(
            "artcraft_plugin.discovery._candidate_dirs", return_value=[Path(empty_dir)]
        ), patch("artcraft_plugin.discovery.shutil.which", return_value=None):
            payload = status_payload()
            self.assertTrue(payload["ok"])
            self.assertNotIn("artcraft_restore_step", payload["capabilities"]["available_tools"])
            self.assertIn("artcraft_restore_step", payload["capabilities"]["unavailable_tools"])

        discovered = {
            "photocraft": BinaryInfo(
                app="photocraft",
                binary_name="photocraft-cli",
                path="/usr/bin/photocraft-cli",
                version="0.23.1",
                available=True,
            ),
            "lightcraft": BinaryInfo("lightcraft", "lightcraft-cli", None, None, False),
            "filmcraft": BinaryInfo("filmcraft", "filmcraft-cli", None, None, False),
            "soundcraft": BinaryInfo("soundcraft", "soundcraft-cli", None, None, False),
        }
        caps_ready = summarize_capabilities(discovered, pillow_available=True)
        self.assertIn("artcraft_restore_step", caps_ready["available_tools"])
        self.assertNotIn("artcraft_restore_step", caps_ready["unavailable_tools"])
        restore_ready = caps_ready["partial_tools"]["artcraft_restore_step"]
        self.assertTrue(restore_ready["available"])
        self.assertTrue(all(r["available"] for r in restore_ready["cli_recipes"].values()))

        caps_no_pil = summarize_capabilities(discovered, pillow_available=False)
        self.assertNotIn("artcraft_restore_step", caps_no_pil["available_tools"])
        self.assertEqual(
            caps_no_pil["unavailable_tools"].get("artcraft_restore_step"),
            "Requires Pillow (PIL)",
        )


if __name__ == "__main__":
    unittest.main()
