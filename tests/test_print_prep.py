"""Unit tests for ArtCraft print preparation tooling."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageCms

from artcraft_plugin.cli import main as cli_main
from artcraft_plugin.print_prep import parse_margin_color, prepare_print
from artcraft_plugin.verify import sha256_file


class TestPrintPrep(unittest.TestCase):
    """Test suite covering print preparation layout, scaling, ICC profiles, and CLI."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.root = Path(self.tmp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_image(
        self,
        name: str,
        size: tuple[int, int],
        color: tuple[int, int, int] = (120, 140, 180),
        icc_profile: bytes | None = None,
        fmt: str = "PNG",
    ) -> Path:
        p = self.root / name
        im = Image.new("RGB", size, color=color)
        save_kwargs = {}
        if icc_profile:
            save_kwargs["icc_profile"] = icc_profile
        im.save(p, format=fmt, **save_kwargs)
        return p

    def test_matching_aspect_ratios(self) -> None:
        """Matching source and target aspect ratios (4:5 source to 8x10 sheet)."""
        src = self._create_image("src_4x5.png", (2400, 3000), color=(100, 150, 200))
        out = self.root / "out_matching.png"

        res = prepare_print(
            input_path=src,
            output_path=out,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            fit_mode="auto",
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "prepared")
        self.assertTrue(out.exists())

        delivery = res["delivery_file"]
        self.assertEqual(delivery["width_px"], 2400)
        self.assertEqual(delivery["height_px"], 3000)
        self.assertEqual(delivery["width_in"], 8.0)
        self.assertEqual(delivery["height_in"], 10.0)
        self.assertEqual(delivery["export_ppi"], 300)
        self.assertEqual(delivery["effective_source_ppi"], 300.0)
        self.assertEqual(delivery["format"], "PNG")
        self.assertTrue(res["aspect_ratio"]["ratios_match"])

        # Preview verification
        preview_p = Path(res["preview_path"])
        self.assertTrue(preview_p.exists())
        self.assertLessEqual(max(res["preview_dimensions"]), 1024)

    def test_conflicting_ratios_clarification_gate(self) -> None:
        """Conflicting aspect ratios (3:4 source to 8x10 sheet) stops at clarification gate."""
        # 3000x4000 has 3:4 aspect ratio. Target 8x10 is 4:5.
        src = self._create_image("src_3x4.png", (3000, 4000), color=(200, 120, 80))
        out = self.root / "out_conflict.png"

        # 1. Without confirmation, must stop without writing output
        res = prepare_print(
            input_path=src,
            output_path=out,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            fit_mode="borderless",
            confirm_crop=False,
        )

        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], "needs_clarification")
        self.assertFalse(
            out.exists(), "No output file should be written when clarification is needed"
        )

        expected_q = (
            "Should the photo fill the 8×10 sheet with a 4:5 crop, "
            "or keep the 3:4 crop and add margins?"
        )
        self.assertEqual(res["question"], expected_q)
        self.assertEqual(res["sheet_size"], "8×10")
        self.assertEqual(res["source_aspect_ratio"], "3:4")
        self.assertEqual(res["target_aspect_ratio"], "4:5")

        # 2. With explicit confirm_crop=True, crop proceeds and outputs verified file
        res_confirmed = prepare_print(
            input_path=src,
            output_path=out,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            fit_mode="borderless",
            confirm_crop=True,
        )

        self.assertTrue(res_confirmed["ok"])
        self.assertEqual(res_confirmed["status"], "prepared")
        self.assertTrue(out.exists())
        self.assertEqual(res_confirmed["delivery_file"]["width_px"], 2400)
        self.assertEqual(res_confirmed["delivery_file"]["height_px"], 3000)

    def test_full_picture_margins(self) -> None:
        """Full-picture margins (fit_mode="margins") preserves entire photo without cropping."""
        src = self._create_image("src_3x4.png", (3000, 4000), color=(50, 150, 50))
        out = self.root / "out_margins.png"

        res = prepare_print(
            input_path=src,
            output_path=out,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            fit_mode="margins",
            margin_color="white",
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "prepared")
        self.assertEqual(res["fit_mode_applied"], "margins")
        self.assertTrue(out.exists())

        delivery = res["delivery_file"]
        self.assertEqual(delivery["width_px"], 2400)
        self.assertEqual(delivery["height_px"], 3000)

        # Reopen to verify canvas margins:
        # Source 3:4 on 4:5 canvas fits vertically: height=3000, width = 3000 * (3/4) = 2250.
        # Margins are (2400 - 2250) // 2 = 75 pixels on left and right.
        with Image.open(out) as im:
            # Margin pixels at edge (0, 1500) should be white (255, 255, 255)
            self.assertEqual(im.getpixel((10, 1500)), (255, 255, 255))
            # Content pixels in center (1200, 1500) should be image color (50, 150, 50)
            self.assertEqual(im.getpixel((1200, 1500)), (50, 150, 50))

    def test_portrait_orientation(self) -> None:
        """Portrait orientation ensures sheet dimensions align with portrait photograph."""
        src = self._create_image("src_portrait.png", (2400, 3200), color=(180, 100, 60))
        out = self.root / "out_portrait.png"

        # Pass sheet dimensions as width=10, height=8 with orientation="portrait"
        res = prepare_print(
            input_path=src,
            output_path=out,
            width_in=10.0,
            height_in=8.0,
            orientation="portrait",
            fit_mode="margins",
            ppi=300,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["orientation_applied"], "portrait")
        delivery = res["delivery_file"]
        self.assertEqual(delivery["width_in"], 8.0)
        self.assertEqual(delivery["height_in"], 10.0)
        self.assertEqual(delivery["width_px"], 2400)
        self.assertEqual(delivery["height_px"], 3000)

    def test_small_sources_and_low_res_warning(self) -> None:
        """Small source reports low effective source PPI separately from export PPI and warns."""
        # 600x750 has 4:5 aspect ratio (matching 8x10).
        # On an 8x10 print, effective source PPI is 600 / 8.0 = 75.0 PPI.
        src = self._create_image("src_small.png", (600, 750), color=(80, 80, 120))
        out = self.root / "out_upscale.png"

        # 1. When allow_upscale=False, raises ValueError
        with self.assertRaises(ValueError) as ctx:
            prepare_print(
                input_path=src,
                output_path=out,
                width_in=8.0,
                height_in=10.0,
                ppi=300,
                allow_upscale=False,
            )
        self.assertIn("allow_upscale=True", str(ctx.exception))
        self.assertFalse(out.exists())

        # 2. When allow_upscale=True, prepares file, reports resolutions, and warns
        res = prepare_print(
            input_path=src,
            output_path=out,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            allow_upscale=True,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "prepared")
        self.assertEqual(res["effective_source_ppi"], 75.0)
        self.assertEqual(res["export_ppi"], 300)
        self.assertEqual(res["export_width_px"], 2400)
        self.assertEqual(res["export_height_px"], 3000)
        self.assertTrue(any("Low source resolution" in w for w in res["warnings"]))
        self.assertTrue(out.exists())

        # Reopen to verify delivery dimensions
        with Image.open(out) as im:
            self.assertEqual(im.size, (2400, 3000))

    def test_color_profile_handling(self) -> None:
        """Embedded ICC profile is preserved into output file and recorded in metadata."""
        srgb_profile = ImageCms.createProfile("sRGB")
        icc_bytes = ImageCms.ImageCmsProfile(srgb_profile).tobytes()

        src = self._create_image(
            "src_icc.png", (2400, 3000), color=(220, 200, 180), icc_profile=icc_bytes
        )
        out = self.root / "out_icc.png"

        res = prepare_print(
            input_path=src,
            output_path=out,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
        )

        self.assertTrue(res["ok"])
        delivery = res["delivery_file"]
        self.assertTrue(delivery["color_profile"]["has_icc_profile"])
        self.assertIn("sRGB", delivery["color_profile"]["icc_profile_name"])

        with Image.open(out) as reopened:
            reopened_icc = reopened.info.get("icc_profile")
            self.assertIsNotNone(reopened_icc)
            self.assertEqual(len(reopened_icc), len(icc_bytes))

    def test_preserve_master_copy(self) -> None:
        """Untouched master copy is saved and checksum matches source."""
        src = self._create_image("src_orig.png", (2400, 3000), color=(10, 20, 30))
        out = self.root / "out_print.png"
        master = self.root / "archive" / "master_copy.png"

        res = prepare_print(
            input_path=src,
            output_path=out,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            preserve_master_path=master,
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["master_copy_path"], str(master.resolve()))
        self.assertTrue(master.exists())
        self.assertEqual(sha256_file(master), sha256_file(src))

    def test_output_formats_jpeg_and_tiff(self) -> None:
        """Supports JPEG and TIFF output formats with correct DPI."""
        src = self._create_image("src.png", (2400, 3000), color=(150, 100, 50))

        # JPEG
        out_jpg = self.root / "out.jpg"
        res_jpg = prepare_print(
            input_path=src, output_path=out_jpg, width_in=8.0, height_in=10.0, ppi=300
        )
        self.assertTrue(res_jpg["ok"])
        self.assertEqual(res_jpg["delivery_file"]["format"], "JPEG")

        # TIFF
        out_tif = self.root / "out.tif"
        res_tif = prepare_print(
            input_path=src, output_path=out_tif, width_in=8.0, height_in=10.0, ppi=300
        )
        self.assertTrue(res_tif["ok"])
        self.assertEqual(res_tif["delivery_file"]["format"], "TIFF")

    def test_safety_guards_overwrite_and_identical_paths(self) -> None:
        """Guards against overwriting existing files and identical source/dest."""
        src = self._create_image("src.png", (2400, 3000))
        out = self.root / "existing.png"
        out.touch()

        # Destination identical to source
        with self.assertRaises(ValueError):
            prepare_print(input_path=src, output_path=src, width_in=8.0, height_in=10.0)

        # Existing destination without overwrite
        with self.assertRaises(FileExistsError):
            prepare_print(input_path=src, output_path=out, width_in=8.0, height_in=10.0)

        # Existing destination with overwrite=True succeeds
        res = prepare_print(
            input_path=src, output_path=out, width_in=8.0, height_in=10.0, overwrite=True
        )
        self.assertTrue(res["ok"])

    def test_cli_prep_print_subcommand(self) -> None:
        """CLI `prep-print` subcommand writes prepared files and stops on unconfirmed crops."""
        src = self._create_image("src_cli.png", (2400, 3000), color=(90, 110, 130))
        out = self.root / "out_cli.png"

        # Matching print command
        code = cli_main(
            ["prep-print", str(src), str(out), "--width", "8.0", "--height", "10.0", "--ppi", "300"]
        )
        self.assertEqual(code, 0)
        self.assertTrue(out.exists())

        # Conflicting print command without confirm-crop returns 0 with needs_clarification
        src_conflict = self._create_image("src_cli_conflict.png", (3000, 4000))
        out_conflict = self.root / "out_cli_conflict.png"
        code_conflict = cli_main([
            "prep-print", str(src_conflict), str(out_conflict),
            "--width", "8.0", "--height", "10.0", "--fit-mode", "borderless"
        ])
        self.assertEqual(code_conflict, 0)
        self.assertFalse(out_conflict.exists())

    def test_rejects_non_positive_dimensions_and_ppi(self) -> None:
        """prepare_print rejects width_in <= 0, height_in <= 0, and ppi <= 0."""
        src = self._create_image("src_dim.png", (600, 600))
        out_dir = self.root / "never_created"
        out = out_dir / "out.png"

        for kwargs in (
            {"width_in": 0, "height_in": 10.0, "ppi": 300},
            {"width_in": 8.0, "height_in": -2.0, "ppi": 300},
            {"width_in": 8.0, "height_in": 10.0, "ppi": 0},
            {"width_in": 8.0, "height_in": 10.0, "ppi": -150},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    prepare_print(input_path=src, output_path=out, **kwargs)
                self.assertFalse(out_dir.exists())

    def test_margins_fit_without_false_upscale_error(self) -> None:
        """Full-picture margins at native 300 PPI must not falsely trigger allow_upscale=True."""
        # 2250x3000 (3:4) inside 8x10 @ 300 PPI (2400x3000): scale is 1.0, effective PPI is 300.0
        src_3x4 = self._create_image("src_2250x3000.png", (2250, 3000), color=(40, 120, 180))
        out_3x4 = self.root / "out_margins_3x4.png"
        res_3x4 = prepare_print(
            input_path=src_3x4,
            output_path=out_3x4,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            fit_mode="margins",
            allow_upscale=False,
        )
        self.assertTrue(res_3x4["ok"])
        self.assertEqual(res_3x4["effective_source_ppi"], 300.0)
        self.assertEqual(res_3x4["warnings"], [])
        self.assertEqual(res_3x4["delivery_file"]["width_px"], 2400)
        self.assertEqual(res_3x4["delivery_file"]["height_px"], 3000)

        # 3000x1500 panorama inside 8x10 @ 300 PPI (3000x2400 landscape): scale is 1.0
        src_pano = self._create_image("src_3000x1500.png", (3000, 1500), color=(90, 60, 150))
        out_pano = self.root / "out_margins_pano.png"
        res_pano = prepare_print(
            input_path=src_pano,
            output_path=out_pano,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            fit_mode="margins",
            allow_upscale=False,
        )
        self.assertTrue(res_pano["ok"])
        self.assertEqual(res_pano["effective_source_ppi"], 300.0)
        self.assertEqual(res_pano["warnings"], [])
        self.assertEqual(res_pano["delivery_file"]["width_px"], 3000)
        self.assertEqual(res_pano["delivery_file"]["height_px"], 2400)

        # Genuinely lower-res 1500x2000 (200 PPI) must still require allow_upscale=True
        src_low = self._create_image("src_1500x2000.png", (1500, 2000))
        with self.assertRaises(ValueError):
            prepare_print(
                input_path=src_low,
                output_path=self.root / "out_low_margins.png",
                width_in=8.0,
                height_in=10.0,
                ppi=300,
                fit_mode="margins",
                allow_upscale=False,
            )

    def test_invalid_margin_color_raises_value_error(self) -> None:
        """Invalid margin_color fails loudly with ValueError instead of defaulting to white."""
        for bad_color in ("not-a-real-color", "", 123, (1, 2), (300, 0, 0), (True, 0, 0)):
            with self.subTest(color=bad_color):
                with self.assertRaises(ValueError):
                    parse_margin_color(bad_color)  # type: ignore[arg-type]

        src = self._create_image("src_bad_margin.png", (2250, 3000))
        out = self.root / "out_bad_margin.png"
        with self.assertRaises(ValueError):
            prepare_print(
                input_path=src,
                output_path=out,
                width_in=8.0,
                height_in=10.0,
                ppi=300,
                fit_mode="margins",
                margin_color="not-a-real-color",
            )
        self.assertFalse(out.exists())

    def test_preserve_master_path_protects_existing_different_and_symlinks(self) -> None:
        """preserve_master_path protects existing differing files and dangling symlinks."""
        src = self._create_image("src_master.png", (2400, 3000), color=(20, 40, 60))
        out = self.root / "out_master_test.png"
        master = self.root / "archive" / "master.png"
        master.parent.mkdir(parents=True, exist_ok=True)
        master.write_bytes(b"precious-different-master")

        with self.assertRaises(FileExistsError):
            prepare_print(
                input_path=src,
                output_path=out,
                width_in=8.0,
                height_in=10.0,
                ppi=300,
                preserve_master_path=master,
            )
        self.assertEqual(master.read_bytes(), b"precious-different-master")
        self.assertFalse(out.exists())

        # Dangling symlink at preserve_master_path must also be refused
        dangling_master = self.root / "archive" / "dangling_master.png"
        dangling_target = self.root / "archive" / "missing_master_target.png"
        os.symlink(dangling_target, dangling_master)
        with self.assertRaises(FileExistsError):
            prepare_print(
                input_path=src,
                output_path=out,
                width_in=8.0,
                height_in=10.0,
                ppi=300,
                preserve_master_path=dangling_master,
            )
        self.assertTrue(os.path.islink(dangling_master))
        self.assertFalse(dangling_target.exists())

        # allow_overwrite=True safely replaces existing master via temp + os.replace
        res = prepare_print(
            input_path=src,
            output_path=out,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            preserve_master_path=master,
            allow_overwrite=True,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(sha256_file(master), sha256_file(src))

    def test_dangling_symlink_output_refused_and_allow_overwrite_standardized(self) -> None:
        """Refuses dangling symlink output paths and supports allow_overwrite=True."""
        src = self._create_image("src_sym_out.png", (2400, 3000))
        dangling = self.root / "dangling_out.png"
        target = self.root / "missing_out_target.png"
        os.symlink(target, dangling)

        with self.assertRaises(FileExistsError):
            prepare_print(
                input_path=src,
                output_path=dangling,
                width_in=8.0,
                height_in=10.0,
                ppi=300,
                allow_overwrite=False,
            )
        self.assertTrue(os.path.islink(dangling))
        self.assertFalse(target.exists())

        # Symlink pointing to src must be refused even with allow_overwrite=True
        sym_src = self.root / "alias_src.png"
        os.symlink(src, sym_src)
        with self.assertRaises(ValueError):
            prepare_print(
                input_path=src,
                output_path=sym_src,
                width_in=8.0,
                height_in=10.0,
                ppi=300,
                allow_overwrite=True,
            )

        # allow_overwrite=True replaces dangling symlink atomically without writing to target
        res = prepare_print(
            input_path=src,
            output_path=dangling,
            width_in=8.0,
            height_in=10.0,
            ppi=300,
            allow_overwrite=True,
        )
        self.assertTrue(res["ok"])
        self.assertFalse(target.exists())
        self.assertFalse(os.path.islink(dangling))
        self.assertTrue(dangling.is_file())

    def test_preview_collision_with_master_rejected_before_writes(self) -> None:
        """Colliding preview_path and preserve_master_path fail before creating any files."""
        src = self._create_image("src_prev_col.png", (2400, 3000))
        out = self.root / "out_prev_col.png"
        shared = self.root / "shared_prev_master.png"

        with self.assertRaises(ValueError):
            prepare_print(
                input_path=src,
                output_path=out,
                width_in=8.0,
                height_in=10.0,
                ppi=300,
                preserve_master_path=shared,
                preview_path=shared,
            )
        self.assertFalse(out.exists())
        self.assertFalse(shared.exists())


if __name__ == "__main__":
    unittest.main()
