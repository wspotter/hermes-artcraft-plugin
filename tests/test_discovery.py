"""Tests for ArtCraft CLI binary discovery."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from artcraft_plugin.discovery import discover_all, find_cli_binary


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
                with patch.dict(os.environ, {"HERMES_PROFILE": "testprofile", "HERMES_HOME": "", "ARTCRAFT_BIN_DIR": ""}):
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
                with patch.dict(os.environ, {"HERMES_PROFILE": "", "HERMES_HOME": "", "ARTCRAFT_BIN_DIR": ""}):
                    with patch("artcraft_plugin.discovery.shutil.which", return_value=None):
                        found = find_cli_binary("soundcraft")
                        self.assertEqual(found, cli_bin)

    def test_discover_all_reports_missing_cleanly(self) -> None:
        with patch("artcraft_plugin.discovery.find_cli_binary", return_value=None):
            res = discover_all()
            self.assertEqual(set(res.keys()), {"photocraft", "lightcraft", "filmcraft", "soundcraft"})
            for info in res.values():
                self.assertFalse(info.available)
                self.assertIsNone(info.path)


if __name__ == "__main__":
    unittest.main()
