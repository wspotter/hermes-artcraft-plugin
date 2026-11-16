"""TDD tests for portable ArtCraft recipe validation, trading, and replay."""

from __future__ import annotations

import json
import os
import stat
import struct
import sys
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from artcraft_plugin import cli, recipes, tools
from artcraft_plugin.discovery import find_cli_binary
from artcraft_plugin.verify import sha256_file


def _write_wav(path: Path, sample_rate: int = 44100, seconds: float = 0.08) -> None:
    """Create a tiny mono 16-bit WAV audio fixture."""
    frames = max(1, int(sample_rate * seconds))
    data = struct.pack("<" + "h" * frames, *([1000] * frames))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)


def _valid_skill_md(name: str, *, description: str = "Apply test workflow.") -> str:
    return (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f'version: "0.1.0"\n'
        f'author: "wspotter"\n'
        f'license: "MIT"\n'
        f"platforms: [linux, macos]\n"
        f"metadata:\n"
        f"  hermes:\n"
        f"    category: creative\n"
        f"    tags: [artcraft, recipe]\n"
        f"    related_skills: [artcraft-router]\n"
        f"---\n\n"
        f"# Recipe: Test\n\n"
        f"## When to Use\n\n- Test fixture.\n\n"
        f"## Prerequisites\n\n- `lightcraft-cli` discoverable.\n\n"
        f"## How to Run\n\n```bash\nhermes artcraft recipe run {name} in.png out.jpg\n```\n\n"
        f"## Procedure\n\n1. Inspect then develop.\n\n"
        f"## Pitfalls\n\n- Keep original path distinct.\n\n"
        f"## Verification\n\n- Confirm unchanged `source_sha256`.\n"
    )


def _valid_manifest(name: str, *, tool: str = "artcraft_develop", app: str = "lightcraft") -> dict:
    return {
        "schema_version": "1.0",
        "name": name,
        "title": "Test Matte",
        "description": "Test deterministic workflow.",
        "version": "0.1.0",
        "author": "wspotter",
        "license": "MIT",
        "app": app,
        "media_type": "photo",
        "default_output_suffix": ".jpg",
        "parameters": {
            "exposure": {"type": "number", "default": 0.2},
            "long_edge": {"type": "integer", "default": 64},
        },
        "steps": [
            {
                "id": "develop",
                "tool": tool,
                "args": {
                    "input_path": "{input}",
                    "output_path": "{output}",
                    "sliders": {"light.exposure": "{params.exposure}"},
                    "long_edge": "{params.long_edge}",
                    "quality": 90,
                },
            }
        ],
    }


class TestRecipeValidationInitAndTrading(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_validate_bundled_recipes_all_pass(self) -> None:
        """All bundled runnable recipe-* packages validate cleanly."""
        listed = recipes.list_recipes(skills_dir=self.root / "empty_user_skills")
        self.assertTrue(listed["ok"])
        names = {r["name"] for r in listed["recipes"] if r.get("has_manifest")}
        self.assertGreaterEqual(len(names), 9)
        for expected in (
            "recipe-faded-tones",
            "recipe-color-cast",
            "recipe-dust-scratches",
            "recipe-noise-grain",
            "recipe-sharpening",
            "recipe-enlargement",
            "recipe-film-matte",
            "recipe-voice-master",
            "recipe-web-clip",
        ):
            self.assertIn(expected, names)

    def test_validate_rejects_leaked_paths_disallowed_tools_and_escapes(self) -> None:
        bad_leak = self.root / "recipe-leak"
        bad_leak.mkdir()
        leak_md = _valid_skill_md("recipe-leak").replace(
            "- Test fixture.", "- Located under /home/stacy/secret.png or 192.168.1.50."
        )
        (bad_leak / "SKILL.md").write_text(leak_md, encoding="utf-8")
        (bad_leak / "recipe.json").write_text(
            json.dumps(_valid_manifest("recipe-leak")), encoding="utf-8"
        )
        res_leak = recipes.validate_recipe(bad_leak)
        self.assertFalse(res_leak["ok"])
        joined = "\n".join(res_leak["errors"])
        self.assertIn("machine-local path", joined)
        self.assertIn("private RFC1918 IP", joined)

        # Disallowed raw CLI tool blocked
        bad_tool = self.root / "recipe-raw"
        bad_tool.mkdir()
        (bad_tool / "SKILL.md").write_text(_valid_skill_md("recipe-raw"), encoding="utf-8")
        (bad_tool / "recipe.json").write_text(
            json.dumps(_valid_manifest("recipe-raw", tool="photocraft_run")),
            encoding="utf-8",
        )
        res_tool = recipes.validate_recipe(bad_tool)
        self.assertFalse(res_tool["ok"])
        self.assertIn("Disallowed recipe step tool", "\n".join(res_tool["errors"]))

        # Path traversal in step output_path template rejected
        bad_path = self.root / "recipe-escape"
        bad_path.mkdir()
        (bad_path / "SKILL.md").write_text(_valid_skill_md("recipe-escape"), encoding="utf-8")
        mf_escape = _valid_manifest("recipe-escape")
        mf_escape["steps"][0]["args"]["output_path"] = "{work_dir}/../../evil.png"
        (bad_path / "recipe.json").write_text(json.dumps(mf_escape), encoding="utf-8")
        res_escape = recipes.validate_recipe(bad_path)
        self.assertFalse(res_escape["ok"])

    def test_init_export_and_import_roundtrip_and_safety_guards(self) -> None:
        dev_skills = self.root / "dev_skills"
        install_skills = self.root / "traded_skills"
        bundle = self.root / "recipe-amber-film.zip"

        # 1. Init scaffolds a valid SKILL.md + recipe.json
        init_res = recipes.init_recipe(
            "amber-film",
            app="lightcraft",
            dest_dir=dev_skills,
            author="wspotter",
            description="Warm amber film look.",
        )
        self.assertTrue(init_res["ok"], init_res)
        recipe_dir = Path(init_res["recipe_dir"])
        self.assertTrue((recipe_dir / "SKILL.md").is_file())
        self.assertTrue((recipe_dir / "recipe.json").is_file())
        self.assertTrue(recipes.validate_recipe(recipe_dir)["ok"])

        # Init refuses overwrite without allow_overwrite=True
        dup_init = recipes.init_recipe("amber-film", app="lightcraft", dest_dir=dev_skills)
        self.assertFalse(dup_init["ok"])

        # 2. Export validates and writes deterministic zip atomically
        exp_res = recipes.export_recipe(recipe_dir, bundle)
        self.assertTrue(exp_res["ok"], exp_res)
        self.assertTrue(bundle.is_file())

        # Export refuses overwrite unless allow_overwrite=True
        dup_exp = recipes.export_recipe(recipe_dir, bundle, allow_overwrite=False)
        self.assertFalse(dup_exp["ok"])

        # Export refuses dirty recipe with private IP
        (recipe_dir / "SKILL.md").write_text(
            _valid_skill_md("recipe-amber-film", description="Warm amber film look.").replace(
                "- Test fixture.", "- Host 10.0.0.5"
            ),
            encoding="utf-8",
        )
        dirty_exp = recipes.export_recipe(recipe_dir, self.root / "dirty.zip")
        self.assertFalse(dirty_exp["ok"])
        self.assertFalse((self.root / "dirty.zip").exists())

        # 3. Import safely installs valid bundle into another skills directory
        imp_res = recipes.import_recipe(bundle, dest_dir=install_skills)
        self.assertTrue(imp_res["ok"], imp_res)
        installed_dir = Path(imp_res["recipe_dir"])
        self.assertTrue((installed_dir / "SKILL.md").is_file())
        self.assertTrue((installed_dir / "recipe.json").is_file())
        self.assertTrue(recipes.validate_recipe(installed_dir)["ok"])

        # Refuses overwriting already-installed recipe unless allow_overwrite=True
        dup_imp = recipes.import_recipe(bundle, dest_dir=install_skills)
        self.assertFalse(dup_imp["ok"])

        # Refuses zip-slip traversal bundle
        slip_zip = self.root / "slip.zip"
        with zipfile.ZipFile(slip_zip, "w") as zf:
            zf.writestr("../../outside.txt", "pwned")
        slip_res = recipes.import_recipe(slip_zip, dest_dir=install_skills)
        self.assertFalse(slip_res["ok"])
        self.assertFalse((self.root / "outside.txt").exists())


class TestRecipeReplayExecution(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_photo_recipe_non_destructive_and_pauses_on_gate(self) -> None:
        """Photo restoration recipe replays multi-step, preserves SHA, and stops on unsafe bounds."""  # noqa: E501
        from PIL import ImageDraw

        src = self.root / "src.png"
        out = self.root / "out.png"
        faded = Image.new("RGB", (64, 64), color=(95, 105, 115))
        ImageDraw.Draw(faded).rectangle([16, 16, 48, 48], fill=(155, 165, 175))
        faded.save(src)
        src_sha = sha256_file(src)

        fake_pc = self.root / "photocraft-cli"
        fake_pc.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "from PIL import Image, ImageOps\n"
            "args = sys.argv[1:]\n"
            "in_p = args[1]\n"
            "out_p = args[args.index('--out') + 1]\n"
            "ImageOps.autocontrast(Image.open(in_p)).save(out_p, format='PNG')\n",
            encoding="utf-8",
        )
        fake_pc.chmod(fake_pc.stat().st_mode | stat.S_IEXEC)

        # Cannot overwrite input_path
        with patch.dict(os.environ, {"ARTCRAFT_BIN_DIR": str(self.root)}):
            same_res = recipes.run_recipe("recipe-faded-tones", src, src)
            self.assertFalse(same_res["ok"])
            self.assertEqual(sha256_file(src), src_sha)

            # Unsafe gamma stops cleanly at gate without publishing out
            gate_res = recipes.run_recipe(
                "recipe-faded-tones",
                src,
                out,
                params={"gamma": 2.4},
                work_dir=self.root / "work_gate",
            )
            self.assertFalse(gate_res["ok"])
            self.assertEqual(gate_res["status"], "needs_decision")
            self.assertFalse(out.exists())

            # Valid replay succeeds, runs inspect + restore + review, keeps source intact
            ok_res = recipes.run_recipe(
                "recipe-faded-tones",
                src,
                out,
                work_dir=self.root / "work_ok",
            )
            self.assertTrue(ok_res["ok"], ok_res)
            self.assertEqual(ok_res["source_sha256"], src_sha)
            self.assertEqual(sha256_file(src), src_sha)
            self.assertTrue(out.is_file())
            self.assertEqual(len(ok_res["steps"]), 3)

    def test_run_audio_and_video_recipes_via_cli_and_tool(self) -> None:
        """SoundCraft and FilmCraft recipes replay deterministically through CLI and tool."""
        wav_src = self.root / "voice.wav"
        wav_out = self.root / "voice_master.wav"
        _write_wav(wav_src)
        wav_sha = sha256_file(wav_src)

        fake_sc = self.root / "soundcraft-cli"
        fake_sc.write_text(
            f"#!{sys.executable}\n"
            "import json, sys, shutil\n"
            "args = sys.argv[1:]\n"
            "if args[0] == 'info':\n"
            "    print(json.dumps({'sample_rate': 48000, 'channels': 1, 'frames': 3528}))\n"
            "elif args[0] == 'convert':\n"
            "    shutil.copy2(args[1], args[2])\n",
            encoding="utf-8",
        )
        fake_sc.chmod(fake_sc.stat().st_mode | stat.S_IEXEC)

        fake_fc = self.root / "filmcraft-cli"
        fake_fc.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "from PIL import Image\n"
            "args = sys.argv[1:]\n"
            "if args[0] == 'probe':\n"
            "    info = {'container': 'MPEG-4', 'video': {'width': 320, 'height': 180}}\n"
            "    print(json.dumps(info))\n"
            "elif args[0] == 'run':\n"
            "    lines = sys.stdin.read().strip().splitlines()\n"
            "    last = json.loads(lines[-1])\n"
            "    out_p = last['params']['path']\n"
            "    if last['id'] == 'file.exportFrame':\n"
            "        Image.new('RGB', (160, 90), color=(30, 60, 90)).save(out_p, format='PNG')\n"
            "    else:\n"
            "        open(out_p, 'wb').write(b'ftypmp42-test')\n"
            "    print(json.dumps({'ok': True}))\n",
            encoding="utf-8",
        )
        fake_fc.chmod(fake_fc.stat().st_mode | stat.S_IEXEC)

        with patch.dict(os.environ, {"ARTCRAFT_BIN_DIR": str(self.root)}):
            rc_aud = cli.main(
                [
                    "recipe",
                    "run",
                    "recipe-voice-master",
                    str(wav_src),
                    str(wav_out),
                    "--work-dir",
                    str(self.root / "aud_work"),
                ]
            )
            self.assertEqual(rc_aud, 0)
            self.assertTrue(wav_out.is_file())
            self.assertEqual(sha256_file(wav_src), wav_sha)

            clip_src = self.root / "clip.mp4"
            clip_out = self.root / "clip_web.mp4"
            clip_src.write_bytes(b"src-mp4")
            clip_sha = sha256_file(clip_src)

            vid_res = json.loads(
                tools.artcraft_recipe(
                    {
                        "action": "run",
                        "recipe": "recipe-web-clip",
                        "input_path": str(clip_src),
                        "output_path": str(clip_out),
                        "work_dir": str(self.root / "vid_work"),
                        "params": {"start_seconds": 0.0, "end_seconds": 1.0},
                    }
                )
            )
            self.assertTrue(vid_res["ok"], vid_res)
            self.assertTrue(clip_out.is_file())
            self.assertEqual(sha256_file(clip_src), clip_sha)
            self.assertEqual([s["id"] for s in vid_res["steps"]], ["probe", "preview", "export"])

    @unittest.skipIf(find_cli_binary("soundcraft") is None, "soundcraft-cli not installed")
    def test_real_soundcraft_voice_master_recipe_replay(self) -> None:
        wav_src = self.root / "real_voice.wav"
        wav_out = self.root / "real_voice_master.wav"
        _write_wav(wav_src, sample_rate=44100, seconds=0.05)
        wav_sha = sha256_file(wav_src)

        res = recipes.run_recipe(
            "recipe-voice-master",
            wav_src,
            wav_out,
            work_dir=self.root / "real_aud_work",
        )
        self.assertTrue(res["ok"], res)
        self.assertEqual(sha256_file(wav_src), wav_sha)
        self.assertEqual(res["steps"][1]["result"]["output_info"]["sample_rate"], 48000)

    @unittest.skipIf(find_cli_binary("lightcraft") is None, "lightcraft-cli not installed")
    def test_real_lightcraft_film_matte_recipe_replay(self) -> None:
        from PIL import ImageDraw

        src = self.root / "real_photo.png"
        out = self.root / "real_photo_matte.jpg"
        im = Image.new("RGB", (128, 128), color=(90, 100, 110))
        ImageDraw.Draw(im).rectangle([24, 24, 104, 104], fill=(170, 180, 190))
        im.save(src)
        src_sha = sha256_file(src)

        res = recipes.run_recipe(
            "recipe-film-matte",
            src,
            out,
            work_dir=self.root / "real_lc_work",
        )
        self.assertTrue(res["ok"], res)
        self.assertEqual(sha256_file(src), src_sha)
        self.assertEqual(len(res["steps"]), 3)
        self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
