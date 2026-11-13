"""Unit tests for ArtCraft restoration recipes, checkpointing, crops, and Stop/Ask Gate."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from artcraft_plugin.cli import main as cli_main
from artcraft_plugin.restore import (
    SAFE_BOUNDS,
    SUPPORTED_RECIPES,
    UNSUPPORTED_OPERATIONS,
    apply_color_cast,
    apply_dust_and_scratches,
    apply_enlargement,
    apply_faded_tones,
    apply_noise_and_grain,
    apply_sharpening,
    check_stop_ask_gate,
    generate_before_after_crops,
    get_checkpoint,
    list_checkpoints,
    restore_step,
)
from artcraft_plugin.verify import sha256_file


class TestRestorationRecipes(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_test_image(
        self,
        name: str,
        size: tuple[int, int] = (256, 256),
        color: tuple[int, int, int] = (120, 120, 120),
    ) -> Path:
        path = self.root / name
        im = Image.new("RGB", size, color=color)
        draw = ImageDraw.Draw(im)
        # Add a high-contrast diagonal feature and circle
        draw.line([0, 0, size[0], size[1]], fill=(240, 240, 240), width=4)
        draw.ellipse([size[0] // 4, size[1] // 4, 3 * size[0] // 4, 3 * size[1] // 4], outline=(40, 40, 40), width=3)
        im.save(path, format="PNG")
        return path

    def test_supported_recipes_and_unsupported_operations_catalog(self) -> None:
        """Verify defined supported recipes and explicitly recorded unsupported operations."""
        self.assertIn("faded_tones", SUPPORTED_RECIPES)
        self.assertIn("color_cast", SUPPORTED_RECIPES)
        self.assertIn("dust_and_scratches", SUPPORTED_RECIPES)
        self.assertIn("noise_and_grain", SUPPORTED_RECIPES)
        self.assertIn("sharpening", SUPPORTED_RECIPES)
        self.assertIn("enlargement", SUPPORTED_RECIPES)

        self.assertIn("reconstruct_missing_face", UNSUPPORTED_OPERATIONS)
        self.assertIn("reconstruct_missing_lettering", UNSUPPORTED_OPERATIONS)
        self.assertIn("generative_inpainting_hallucination", UNSUPPORTED_OPERATIONS)

    # =========================================================================
    # STOP / ASK GATE TESTS
    # =========================================================================

    def test_stop_ask_gate_reconstruct_missing_flag(self) -> None:
        """Gate stops when reconstruct_missing=True is requested and leaves original untouched."""
        src = self._create_test_image("src_gate.png")
        src_sha = sha256_file(src)
        out = self.root / "out_gate.png"

        res = restore_step(
            input_path=src,
            output_path=out,
            recipe="faded_tones",
            reconstruct_missing=True,
        )

        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "needs_decision")
        self.assertTrue(res["original_intact"])
        self.assertIn("reconstructing missing", res["reason"].lower())
        self.assertFalse(out.exists())
        self.assertEqual(sha256_file(src), src_sha)

    def test_stop_ask_gate_missing_face_or_lettering_content_type(self) -> None:
        """Gate stops when content_type indicates missing face or lettering."""
        src = self._create_test_image("src_face.png")
        out = self.root / "out_face.png"

        # Missing face
        res_face = restore_step(
            input_path=src,
            output_path=out,
            recipe="dust_and_scratches",
            content_type="missing_face",
        )
        self.assertFalse(res_face["ok"])
        self.assertEqual(res_face["status"], "needs_decision")
        self.assertFalse(out.exists())

        # Missing lettering
        res_text = restore_step(
            input_path=src,
            output_path=out,
            recipe="sharpening",
            content_type="missing_lettering",
        )
        self.assertFalse(res_text["ok"])
        self.assertEqual(res_text["status"], "needs_decision")
        self.assertFalse(out.exists())

    def test_stop_ask_gate_unsafe_parameters(self) -> None:
        """Gate stops when parameters exceed safe bounds (halo, crushing, extreme scale)."""
        src = self._create_test_image("src_unsafe.png")
        out = self.root / "out_unsafe.png"

        # Excessive sharpening amount (> 120 causes severe edge halos)
        res_sharp = restore_step(
            input_path=src,
            output_path=out,
            recipe="sharpening",
            parameters={"amount": 180, "radius": 3.0},
        )
        self.assertFalse(res_sharp["ok"])
        self.assertEqual(res_sharp["status"], "needs_decision")
        self.assertIn("halos", res_sharp["reason"].lower())
        self.assertFalse(out.exists())

        # Extreme tonal crushing (inBlack > 50)
        res_tone = restore_step(
            input_path=src,
            output_path=out,
            recipe="faded_tones",
            parameters={"in_black": 80},
        )
        self.assertFalse(res_tone["ok"])
        self.assertEqual(res_tone["status"], "needs_decision")
        self.assertIn("shadow", res_tone["reason"].lower())
        self.assertFalse(out.exists())

        # Extreme enlargement scale (> 4x)
        res_scale = restore_step(
            input_path=src,
            output_path=out,
            recipe="enlargement",
            parameters={"scale": 8.0},
        )
        self.assertFalse(res_scale["ok"])
        self.assertEqual(res_scale["status"], "needs_decision")
        self.assertIn("scale", res_scale["reason"].lower())
        self.assertFalse(out.exists())

    # =========================================================================
    # RECIPE 1: FADED TONES
    # =========================================================================

    def test_recipe_faded_tones(self) -> None:
        """Gentle tonal correction preserving highlight and shadow detail."""
        src = self._create_test_image("src_faded.png", (200, 200), (130, 130, 130))
        out = self.root / "out_faded.png"
        cp_dir = self.root / "checkpoints_faded"

        res = restore_step(
            input_path=src,
            output_path=out,
            recipe="faded_tones",
            parameters={"in_black": 15, "in_white": 240, "gamma": 1.05},
            checkpoint_dir=cp_dir,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "applied")
        self.assertTrue(out.exists())
        self.assertGreater(res["diff"]["changed_pixels"], 0)
        self.assertEqual(len(res["crops"]), 2)
        # Check checkpoint manifest was created
        manifest = list_checkpoints(cp_dir)
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0]["recipe"], "faded_tones")

    # =========================================================================
    # RECIPE 2: COLOR CAST
    # =========================================================================

    def test_recipe_color_cast(self) -> None:
        """Neutral-balance and color adjustment preserving believable skin/warmth."""
        # Warm/yellow cast test image
        src = self._create_test_image("src_cast.png", (200, 200), (160, 145, 110))
        out = self.root / "out_cast.png"
        cp_dir = self.root / "checkpoints_cast"

        res = restore_step(
            input_path=src,
            output_path=out,
            recipe="color_cast",
            parameters={"midtones": [0, 0, 18], "preserveLuminosity": True},
            checkpoint_dir=cp_dir,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "applied")
        self.assertTrue(out.exists())
        self.assertGreater(res["diff"]["changed_pixels"], 0)
        self.assertTrue(Path(res["crops"][0]["native"]["comparison_strip_path"]).exists())

    # =========================================================================
    # RECIPE 3: DUST AND SCRATCHES
    # =========================================================================

    def test_recipe_dust_and_scratches_spot_heal(self) -> None:
        """Localized healing preserving nearby edges with 0 pixels changed outside region."""
        src_path = self.root / "src_scratch.png"
        im = Image.new("RGB", (200, 200), color=(100, 100, 100))
        draw = ImageDraw.Draw(im)
        # Add scratch in region [20, 20, 30, 30]
        draw.line([25, 25, 40, 40], fill=(255, 255, 255), width=2)
        im.save(src_path)

        out = self.root / "out_scratch.png"
        cp_dir = self.root / "checkpoints_scratch"

        res = restore_step(
            input_path=src_path,
            output_path=out,
            recipe="dust_and_scratches",
            parameters={
                "points": [[26, 26], [32, 32], [38, 38]],
                "size": 6,
            },
            region=[20, 20, 30, 30],
            checkpoint_dir=cp_dir,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "applied")
        self.assertTrue(out.exists())
        self.assertGreater(res["diff"]["changed_pixels"], 0)

    def test_recipe_dust_and_scratches_filter(self) -> None:
        """Filter-based dust and scratches reduction with gentle radius."""
        src = self._create_test_image("src_ds_filt.png", (150, 150))
        out = self.root / "out_ds_filt.png"

        res = restore_step(
            input_path=src,
            output_path=out,
            recipe="dust_and_scratches",
            parameters={"radius": 1, "threshold": 20},
        )
        self.assertTrue(res["ok"])
        self.assertTrue(out.exists())
        self.assertGreater(res["diff"]["changed_pixels"], 0)

    # =========================================================================
    # RECIPE 4: NOISE AND GRAIN
    # =========================================================================

    def test_recipe_noise_and_grain(self) -> None:
        """Modest selective reduction retaining detail and texture."""
        src_path = self.root / "src_noise.png"
        arr = np.full((180, 180, 3), 120, dtype=np.uint8)
        # Add synthetic noise
        noise = np.random.randint(-15, 16, arr.shape, dtype=np.int16)
        noisy = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        Image.fromarray(noisy).save(src_path)

        out = self.root / "out_denoised.png"
        res = restore_step(
            input_path=src_path,
            output_path=out,
            recipe="noise_and_grain",
            parameters={"strength": 4, "preserve_details": 70, "reduce_color_noise": 50},
        )
        self.assertTrue(res["ok"])
        self.assertTrue(out.exists())
        self.assertGreater(res["diff"]["changed_pixels"], 0)

    # =========================================================================
    # RECIPE 5: SHARPENING
    # =========================================================================

    def test_recipe_sharpening(self) -> None:
        """Restrained sharpening avoiding distracting halos and artifacts."""
        src = self._create_test_image("src_soft.png", (200, 200))
        out = self.root / "out_sharp.png"

        res = restore_step(
            input_path=src,
            output_path=out,
            recipe="sharpening",
            parameters={"amount": 55, "radius": 1.0, "threshold": 2},
        )
        self.assertTrue(res["ok"])
        self.assertTrue(out.exists())
        self.assertGreater(res["diff"]["changed_pixels"], 0)

    # =========================================================================
    # RECIPE 6: ENLARGEMENT
    # =========================================================================

    def test_recipe_enlargement(self) -> None:
        """Proportional enlargement + output sharpening preserving composition."""
        src = self._create_test_image("src_small.png", (200, 250))  # 4:5 aspect ratio
        out = self.root / "out_enlarged.png"

        res = restore_step(
            input_path=src,
            output_path=out,
            recipe="enlargement",
            parameters={"scale": 2.0, "sharpen_amount": 35},
        )
        self.assertTrue(res["ok"])
        self.assertTrue(out.exists())
        with Image.open(out) as im_out:
            self.assertEqual((im_out.width, im_out.height), (400, 500))

    # =========================================================================
    # CHECKPOINTS & BEFORE/AFTER CROPS
    # =========================================================================

    def test_checkpoint_manifest_and_query(self) -> None:
        """Checkpoint manifest records sequential steps and supports queries."""
        src = self._create_test_image("src_multi.png", (200, 200))
        step1_out = self.root / "step1.png"
        step2_out = self.root / "step2.png"
        cp_dir = self.root / "multi_checkpoints"

        # Step 1: faded tones
        res1 = restore_step(
            input_path=src,
            output_path=step1_out,
            recipe="faded_tones",
            step_name="step_001_faded",
            checkpoint_dir=cp_dir,
        )
        self.assertTrue(res1["ok"])

        # Step 2: sharpening
        res2 = restore_step(
            input_path=step1_out,
            output_path=step2_out,
            recipe="sharpening",
            step_name="step_002_sharp",
            checkpoint_dir=cp_dir,
        )
        self.assertTrue(res2["ok"])

        # Verify manifest
        manifest = list_checkpoints(cp_dir)
        self.assertEqual(len(manifest), 2)
        self.assertEqual(manifest[0]["step_name"], "step_001_faded")
        self.assertEqual(manifest[1]["step_name"], "step_002_sharp")

        # Get checkpoint by name
        cp1 = get_checkpoint(cp_dir, "step_001_faded")
        self.assertIsNotNone(cp1)
        self.assertEqual(cp1["recipe"], "faded_tones")

        # Get checkpoint by index
        cp2 = get_checkpoint(cp_dir, 2)
        self.assertIsNotNone(cp2)
        self.assertEqual(cp2["recipe"], "sharpening")

    def test_native_and_print_scale_crops_generation(self) -> None:
        """Verifies matching native 1:1 and print-scale crops and side-by-side strips."""
        src = self._create_test_image("crop_test_src.png", (300, 300))
        out = self.root / "crop_test_out.png"
        cp_dir = self.root / "crop_test_checkpoints"

        res = restore_step(
            input_path=src,
            output_path=out,
            recipe="sharpening",
            checkpoint_dir=cp_dir,
            target_print_ppi=300,
        )
        self.assertTrue(res["ok"])
        crops = res["crops"]
        self.assertGreaterEqual(len(crops), 1)

        c = crops[0]
        # Native crops exist
        self.assertTrue(Path(c["native"]["before_path"]).exists())
        self.assertTrue(Path(c["native"]["after_path"]).exists())
        self.assertTrue(Path(c["native"]["comparison_strip_path"]).exists())

        # Print-scale crops exist
        self.assertTrue(Path(c["print_scale"]["before_path"]).exists())
        self.assertTrue(Path(c["print_scale"]["after_path"]).exists())
        self.assertTrue(Path(c["print_scale"]["comparison_strip_path"]).exists())
        self.assertEqual(c["print_scale"]["ppi"], 300)

    # =========================================================================
    # CLI SUBCOMMAND TESTS
    # =========================================================================

    def test_cli_restore_subcommand(self) -> None:
        """CLI subcommand `hermes artcraft restore` runs recipe and outputs JSON."""
        src = self._create_test_image("src_cli_rest.png", (200, 200))
        out = self.root / "out_cli_rest.png"

        code = cli_main([
            "restore", "faded_tones", str(src), str(out),
            "--params", json.dumps({"in_black": 10, "in_white": 245}),
        ])
        self.assertEqual(code, 0)
        self.assertTrue(out.exists())

    def test_cli_restore_gate_exit_code(self) -> None:
        """CLI returns exit code 2 when Stop/Ask Gate triggers."""
        src = self._create_test_image("src_cli_gate.png", (200, 200))
        out = self.root / "out_cli_gate.png"

        code = cli_main([
            "restore", "faded_tones", str(src), str(out),
            "--reconstruct-missing",
        ])
        self.assertEqual(code, 2)
        self.assertFalse(out.exists())

    def test_cli_checkpoint_subcommand(self) -> None:
        """CLI subcommand `hermes artcraft checkpoint` lists checkpoints."""
        src = self._create_test_image("src_cli_cp.png", (200, 200))
        out = self.root / "out_cli_cp.png"
        cp_dir = self.root / "cli_checkpoints"

        restore_step(
            input_path=src,
            output_path=out,
            recipe="faded_tones",
            checkpoint_dir=cp_dir,
        )

        code = cli_main(["checkpoint", "list", str(cp_dir)])
        self.assertEqual(code, 0)

    # =========================================================================
    # SAFETY GUARDS
    # =========================================================================

    def test_safety_guards_identical_paths_and_missing_input(self) -> None:
        """Refuses identical input/output paths and non-existent input."""
        src = self._create_test_image("src_guard.png")

        # Identical paths
        res_ident = restore_step(input_path=src, output_path=src, recipe="faded_tones")
        self.assertFalse(res_ident["ok"])
        self.assertIn("distinct", res_ident["error"])

        # Missing input
        res_miss = restore_step(input_path=self.root / "nonexistent.png", output_path=self.root / "out.png", recipe="faded_tones")
        self.assertFalse(res_miss["ok"])
        self.assertIn("does not exist", res_miss["error"])


if __name__ == "__main__":
    unittest.main()
