"""Unit and real-CLI integration tests for LightCraft, SoundCraft, and FilmCraft suite basics."""

from __future__ import annotations

import json
import math
import os
import stat
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from artcraft_plugin import cli, tools
from artcraft_plugin.discovery import find_cli_binary
from artcraft_plugin.runner import atomic_replace_file, run_artcraft_cli
from artcraft_plugin.suite_basics import (
    _atomic_promote,
    filmcraft_video_basic,
    lightcraft_develop,
    soundcraft_audio_basic,
)
from artcraft_plugin.verify import sha256_file


def _write_test_wav(path: Path, sample_rate: int = 44100, seconds: float = 0.1) -> None:
    """Create a mono 16-bit PCM sine wave WAV test fixture."""
    n_frames = max(1, int(sample_rate * seconds))
    samples = [
        int(12000 * math.sin(2.0 * math.pi * 440.0 * idx / sample_rate))
        for idx in range(n_frames)
    ]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))


class TestSuiteBasicsUnit(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_lightcraft_develop_guards_and_mocked_cli(self) -> None:
        src = self.root / "input.png"
        out = self.root / "developed.jpg"
        Image.new("RGB", (200, 100), color=(90, 130, 170)).save(src)
        src_sha = sha256_file(src)

        # Missing input
        res_missing = lightcraft_develop(str(self.root / "missing.png"), str(out))
        self.assertFalse(res_missing["ok"])
        self.assertIn("does not exist", res_missing["error"])

        # Same input and output path refused
        res_same = lightcraft_develop(str(src), str(src))
        self.assertFalse(res_same["ok"])
        self.assertIn("non_destructive_guard", res_same["error"])

        # Pre-existing output refused without allow_overwrite
        out.write_bytes(b"existing")
        res_exists = lightcraft_develop(str(src), str(out), allow_overwrite=False)
        self.assertFalse(res_exists["ok"])
        self.assertIn("already exists", res_exists["error"])
        out.unlink()

        # Mocked lightcraft-cli binary
        fake_lc = self.root / "lightcraft-cli"
        fake_lc.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "from PIL import Image\n"
            "args = sys.argv[1:]\n"
            "out_idx = args.index('-o') + 1\n"
            "Image.new('RGB', (100, 50), color=(200, 150, 100)).save(\n"
            "    args[out_idx], format='JPEG'\n"
            ")\n",
            encoding="utf-8",
        )
        fake_lc.chmod(fake_lc.stat().st_mode | stat.S_IEXEC)

        with patch("artcraft_plugin.suite_basics.find_cli_binary", return_value=fake_lc):
            res_ok = lightcraft_develop(
                str(src),
                str(out),
                sliders={"light.exposure": 0.5, "light.contrast": 10},
                preset="punchy",
                long_edge=100,
                quality=90,
                export_options={"ppi": 300},
            )
            self.assertTrue(res_ok["ok"], res_ok)
            self.assertEqual(res_ok["app"], "lightcraft")
            self.assertEqual(res_ok["source_sha256"], src_sha)
            self.assertEqual(sha256_file(src), src_sha)
            self.assertEqual(res_ok["width"], 100)
            self.assertEqual(res_ok["height"], 50)
            self.assertTrue(out.is_file())

    def test_soundcraft_audio_basic_guards_and_mocked_cli(self) -> None:
        src = self.root / "in.wav"
        out = self.root / "out.wav"
        _write_test_wav(src)
        src_sha = sha256_file(src)

        # Invalid action
        self.assertFalse(soundcraft_audio_basic("bad", str(src))["ok"])

        # Missing input
        self.assertFalse(soundcraft_audio_basic("info", str(self.root / "no.wav"))["ok"])

        # Convert without output_path
        self.assertFalse(soundcraft_audio_basic("convert", str(src))["ok"])

        # Convert with invalid bit_depth
        self.assertFalse(
            soundcraft_audio_basic("convert", str(src), output_path=str(out), bit_depth="8")["ok"]
        )

        # Mocked soundcraft-cli binary
        fake_sc = self.root / "soundcraft-cli"
        fake_sc.write_text(
            f"#!{sys.executable}\n"
            "import json, shutil, sys\n"
            "cmd = sys.argv[1]\n"
            "if cmd == 'info':\n"
            "    payload = {\n"
            "        'bwf': None, 'channels': 1, 'format': 'Wav', 'frames': 4800,\n"
            "        'sample_format': 'Int16', 'sample_rate': 48000, 'seconds': 0.1,\n"
            "    }\n"
            "    print(json.dumps(payload))\n"
            "elif cmd == 'convert':\n"
            "    shutil.copyfile(sys.argv[2], sys.argv[3])\n",
            encoding="utf-8",
        )
        fake_sc.chmod(fake_sc.stat().st_mode | stat.S_IEXEC)

        with patch("artcraft_plugin.suite_basics.find_cli_binary", return_value=fake_sc):
            info_res = soundcraft_audio_basic("info", str(src))
            self.assertTrue(info_res["ok"], info_res)
            self.assertEqual(info_res["source_sha256"], src_sha)
            self.assertEqual(info_res["info"]["sample_rate"], 48000)

            conv_res = soundcraft_audio_basic(
                "convert",
                str(src),
                output_path=str(out),
                sample_rate=48000,
                bit_depth="16",
                normalize=True,
                dither=False,
            )
            self.assertTrue(conv_res["ok"], conv_res)
            self.assertEqual(conv_res["source_sha256"], src_sha)
            self.assertEqual(sha256_file(src), src_sha)
            self.assertTrue(out.is_file())

    def test_filmcraft_video_basic_guards_and_mocked_cli(self) -> None:
        clip = self.root / "clip.mp4"
        clip.write_bytes(b"fake-mp4-content")
        clip_sha = sha256_file(clip)

        # Invalid action
        self.assertFalse(filmcraft_video_basic("unknown")["ok"])

        # Probe without input_path
        self.assertFalse(filmcraft_video_basic("probe")["ok"])

        # Render frame without output_path
        self.assertFalse(filmcraft_video_basic("render_frame", input_path=str(clip))["ok"])

        # Export without any source
        self.assertFalse(
            filmcraft_video_basic("export", output_path=str(self.root / "o.mp4"))["ok"]
        )

        fake_fc = self.root / "filmcraft-cli"
        fake_fc.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "from PIL import Image\n"
            "args = sys.argv[1:]\n"
            "if 'probe' in args:\n"
            "    info = {\n"
            "        'container': 'MPEG-4',\n"
            "        'kind': 'Movie',\n"
            "        'video': {'width': 320, 'height': 180},\n"
            "    }\n"
            "    print(json.dumps(info))\n"
            "elif 'run' in args:\n"
            "    data = sys.stdin.read().strip().splitlines()\n"
            "    last = json.loads(data[-1])\n"
            "    out_p = last['params']['path']\n"
            "    if last['id'] == 'file.exportFrame':\n"
            "        Image.new('RGB', (320, 180), color=(40, 80, 120)).save(out_p, format='PNG')\n"
            "    else:\n"
            "        open(out_p, 'wb').write(b'exported-mp4-bytes')\n"
            "    for idx, line in enumerate(data, 1):\n"
            "        obj = json.loads(line)\n"
            "        print(json.dumps({'id': obj['id'], 'line': idx, 'ok': True, 'result': {}}))\n",
            encoding="utf-8",
        )
        fake_fc.chmod(fake_fc.stat().st_mode | stat.S_IEXEC)

        with patch("artcraft_plugin.suite_basics.find_cli_binary", return_value=fake_fc):
            p_res = filmcraft_video_basic("probe", input_path=str(clip))
            self.assertTrue(p_res["ok"], p_res)
            self.assertEqual(p_res["probe"]["container"], "MPEG-4")
            self.assertEqual(sha256_file(clip), clip_sha)

            frame_out = self.root / "frame.png"
            rf_res = filmcraft_video_basic(
                "render_frame",
                input_path=str(clip),
                output_path=str(frame_out),
                seconds=0.25,
                scale=0.5,
            )
            self.assertTrue(rf_res["ok"], rf_res)
            self.assertEqual(rf_res["width"], 160)
            self.assertEqual(rf_res["height"], 90)
            self.assertEqual(sha256_file(clip), clip_sha)

            exp_out = self.root / "trimmed.mp4"
            ex_res = filmcraft_video_basic(
                "export",
                input_path=str(clip),
                output_path=str(exp_out),
                start_seconds=0.0,
                end_seconds=0.5,
                no_audio=True,
            )
            self.assertTrue(ex_res["ok"], ex_res)
            self.assertGreater(ex_res["size_bytes"], 0)
            self.assertEqual(sha256_file(clip), clip_sha)

    def test_runner_guards_dangling_symlink_and_atomic_replace_file(self) -> None:
        """Shared runner guards refuse dangling symlinks before mkdir and promote atomically."""
        src = self.root / "src.png"
        Image.new("RGB", (32, 32), color=(10, 20, 30)).save(src)

        # atomic_replace_file rejects existing file and dangling symlink when allow_overwrite=False
        staged = self.root / "staged.png"
        staged.write_bytes(b"new-bytes")
        dangling = self.root / "dangling.png"
        dangling_target = self.root / "missing_target.png"
        os.symlink(dangling_target, dangling)

        with self.assertRaises(FileExistsError):
            atomic_replace_file(staged, dangling, allow_overwrite=False)
        self.assertTrue(os.path.islink(dangling))
        self.assertFalse(dangling_target.exists())

        with self.assertRaises(FileExistsError):
            _atomic_promote(staged, dangling, allow_overwrite=False)

        # allow_overwrite=True replaces dangling symlink atomically via os.replace
        atomic_replace_file(staged, dangling, allow_overwrite=True)
        self.assertFalse(os.path.islink(dangling))
        self.assertEqual(dangling.read_bytes(), b"new-bytes")
        self.assertFalse(dangling_target.exists())

        # run_artcraft_cli checks identical paths & dangling symlinks BEFORE mkdir
        fake_pc = self.root / "photocraft-cli"
        fake_pc.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_pc.chmod(fake_pc.stat().st_mode | stat.S_IEXEC)

        never_dir = self.root / "never_created"
        same_target = never_dir / "img.png"
        with patch("artcraft_plugin.runner.find_cli_binary", return_value=fake_pc):
            res_same = run_artcraft_cli(
                "photocraft",
                ["--version"],
                input_path=str(same_target),
                output_path=str(same_target),
            )
            self.assertFalse(res_same["ok"])
            self.assertIn("non_destructive_guard", res_same["error"])
            self.assertFalse(never_dir.exists())

            dangling_cli = self.root / "dangling_cli.png"
            os.symlink(self.root / "missing_cli_target.png", dangling_cli)
            res_dangling = run_artcraft_cli(
                "photocraft",
                ["--version"],
                input_path=str(src),
                output_path=str(dangling_cli),
            )
            self.assertFalse(res_dangling["ok"])
            self.assertIn("already exists", res_dangling["error"])

        # suite_basics wrappers also refuse dangling symlinks when allow_overwrite=False
        dangling_lc = self.root / "dangling_lc.jpg"
        os.symlink(self.root / "missing_lc_target.jpg", dangling_lc)
        res_lc = lightcraft_develop(str(src), str(dangling_lc), allow_overwrite=False)
        self.assertFalse(res_lc["ok"])
        self.assertIn("already exists", res_lc["error"])

        wav_in = self.root / "in_guard.wav"
        _write_test_wav(wav_in)
        dangling_sc = self.root / "dangling_sc.wav"
        os.symlink(self.root / "missing_sc_target.wav", dangling_sc)
        with patch("artcraft_plugin.suite_basics.find_cli_binary", return_value=fake_pc):
            res_sc = soundcraft_audio_basic(
                "convert",
                str(wav_in),
                output_path=str(dangling_sc),
                allow_overwrite=False,
            )
        self.assertFalse(res_sc["ok"])
        self.assertIn("already exists", res_sc["error"])

        clip = self.root / "clip_guard.mp4"
        clip.write_bytes(b"fake-mp4")
        dangling_fc = self.root / "dangling_fc.png"
        os.symlink(self.root / "missing_fc_target.png", dangling_fc)
        with patch("artcraft_plugin.suite_basics.find_cli_binary", return_value=fake_pc):
            res_fc = filmcraft_video_basic(
                "render_frame",
                input_path=str(clip),
                output_path=str(dangling_fc),
                allow_overwrite=False,
            )
        self.assertFalse(res_fc["ok"])
        self.assertIn("already exists", res_fc["error"])


class TestSuiteBasicsRealCLIs(unittest.TestCase):
    """Integration tests running against the real installed ArtCraft CLI binaries."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @unittest.skipIf(find_cli_binary("lightcraft") is None, "lightcraft-cli not installed")
    def test_real_lightcraft_develop_via_tool_and_cli(self) -> None:
        src = self.root / "photo.png"
        out = self.root / "developed.jpg"
        Image.new("RGB", (240, 160), color=(110, 90, 70)).save(src)
        src_sha = sha256_file(src)

        res = json.loads(
            tools.artcraft_develop(
                {
                    "input_path": str(src),
                    "output_path": str(out),
                    "sliders": {"light.exposure": 0.4, "light.contrast": 12},
                    "long_edge": 120,
                    "quality": 90,
                }
            )
        )
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["source_sha256"], src_sha)
        self.assertEqual(sha256_file(src), src_sha)
        self.assertEqual(res["width"], 120)
        self.assertEqual(res["height"], 80)
        self.assertTrue(out.is_file())

        # Also test CLI subcommand
        out_cli = self.root / "developed_cli.png"
        rc = cli.main(
            ["develop", str(src), str(out_cli), "--set", "light.exposure=0.2", "--size", "120"]
        )
        self.assertEqual(rc, 0)
        self.assertTrue(out_cli.is_file())
        self.assertEqual(sha256_file(src), src_sha)

    @unittest.skipIf(find_cli_binary("soundcraft") is None, "soundcraft-cli not installed")
    def test_real_soundcraft_audio_basic_info_and_convert(self) -> None:
        src = self.root / "tone_44k.wav"
        out = self.root / "tone_48k.wav"
        _write_test_wav(src, sample_rate=44100, seconds=0.1)
        src_sha = sha256_file(src)

        info_res = json.loads(
            tools.artcraft_audio_basic({"action": "info", "input_path": str(src)})
        )
        self.assertTrue(info_res["ok"], info_res)
        self.assertEqual(info_res["info"]["sample_rate"], 44100)
        self.assertEqual(info_res["info"]["channels"], 1)
        self.assertEqual(sha256_file(src), src_sha)

        conv_res = json.loads(
            tools.artcraft_audio_basic(
                {
                    "action": "convert",
                    "input_path": str(src),
                    "output_path": str(out),
                    "sample_rate": 48000,
                    "bit_depth": "16",
                    "normalize": True,
                    "dither": False,
                }
            )
        )
        self.assertTrue(conv_res["ok"], conv_res)
        self.assertEqual(conv_res["source_sha256"], src_sha)
        self.assertEqual(sha256_file(src), src_sha)
        self.assertEqual(conv_res["output_info"]["sample_rate"], 48000)
        self.assertTrue(out.is_file())

    @unittest.skipIf(find_cli_binary("filmcraft") is None, "filmcraft-cli not installed")
    def test_real_filmcraft_video_basic_probe_render_and_export(self) -> None:
        # 1. Export a short clip from the built-in procedural demo
        demo_clip = self.root / "demo_clip.mp4"
        exp_demo = json.loads(
            tools.artcraft_video_basic(
                {
                    "action": "export",
                    "demo": True,
                    "output_path": str(demo_clip),
                    "start_seconds": 0.0,
                    "end_seconds": 0.5,
                    "scale": 0.25,
                }
            )
        )
        self.assertTrue(exp_demo["ok"], exp_demo)
        self.assertTrue(demo_clip.is_file())
        clip_sha = sha256_file(demo_clip)

        # 2. Probe the exported clip
        probe_res = json.loads(
            tools.artcraft_video_basic({"action": "probe", "input_path": str(demo_clip)})
        )
        self.assertTrue(probe_res["ok"], probe_res)
        self.assertEqual(probe_res["source_sha256"], clip_sha)
        self.assertIn("video", probe_res["probe"])

        # 3. Render a still frame from the standalone clip
        frame_png = self.root / "still.png"
        frame_res = json.loads(
            tools.artcraft_video_basic(
                {
                    "action": "render_frame",
                    "input_path": str(demo_clip),
                    "output_path": str(frame_png),
                    "seconds": 0.1,
                }
            )
        )
        self.assertTrue(frame_res["ok"], frame_res)
        self.assertTrue(frame_png.is_file())
        self.assertGreater(frame_res["width"], 0)
        self.assertEqual(sha256_file(demo_clip), clip_sha)

        # 4. Export a trimmed subclip from the standalone clip via 3-line JSONL
        trimmed_clip = self.root / "trimmed.mp4"
        trim_res = json.loads(
            tools.artcraft_video_basic(
                {
                    "action": "export",
                    "input_path": str(demo_clip),
                    "output_path": str(trimmed_clip),
                    "start_seconds": 0.0,
                    "end_seconds": 0.25,
                    "no_audio": True,
                }
            )
        )
        self.assertTrue(trim_res["ok"], trim_res)
        self.assertTrue(trimmed_clip.is_file())
        self.assertGreater(trim_res["size_bytes"], 0)
        self.assertEqual(sha256_file(demo_clip), clip_sha)


if __name__ == "__main__":
    unittest.main()
