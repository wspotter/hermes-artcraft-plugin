"""Tests for photograph inspection: preview, native crops, print PPI, and measured clues."""

from __future__ import annotations

import argparse
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageCms

from artcraft_plugin import review
from artcraft_plugin.cli import _cmd_inspect
from artcraft_plugin.inspect import (
    MEASUREMENT_LIMITS,
    compute_effective_ppi,
    compute_laplacian,
    compute_laplacian_variance,
    compute_measured_clues,
    determine_aspect_ratio,
    determine_orientation,
    extract_color_profile,
    generate_native_crops,
    generate_preview,
    prepare_inspection,
)
from artcraft_plugin.verify import sha256_file


class TestInspect(unittest.TestCase):
    def test_orientation_and_aspect_ratio(self) -> None:
        self.assertEqual(determine_orientation(800, 600), "landscape")
        self.assertEqual(determine_orientation(600, 800), "portrait")
        self.assertEqual(determine_orientation(500, 500), "square")

        aspect_4_3 = determine_aspect_ratio(800, 600)
        self.assertEqual(aspect_4_3["standard_label"], "4:3")
        self.assertEqual(aspect_4_3["simplified_ratio"], "4:3")

        aspect_16_9 = determine_aspect_ratio(1920, 1080)
        self.assertEqual(aspect_16_9["standard_label"], "16:9")
        self.assertEqual(aspect_16_9["simplified_ratio"], "16:9")

        aspect_sq = determine_aspect_ratio(1000, 1000)
        self.assertEqual(aspect_sq["standard_label"], "1:1")

    def test_color_profile_detection(self) -> None:
        # Image without ICC profile
        img_no_icc = Image.new("RGB", (50, 50), "white")
        res_no_icc = extract_color_profile(img_no_icc)
        self.assertFalse(res_no_icc["has_icc_profile"])
        self.assertIsNone(res_no_icc["icc_profile_name"])

        # Image with embedded sRGB ICC profile
        srgb = ImageCms.createProfile("sRGB")
        icc_bytes = ImageCms.ImageCmsProfile(srgb).tobytes()
        with tempfile.TemporaryDirectory() as tmp:
            icc_file = Path(tmp) / "with_icc.jpg"
            img_no_icc.save(icc_file, format="JPEG", icc_profile=icc_bytes)
            with Image.open(icc_file) as loaded:
                res_icc = extract_color_profile(loaded)
                self.assertTrue(res_icc["has_icc_profile"])
                self.assertIsNotNone(res_icc["icc_profile_name"])
                self.assertIn("sRGB", res_icc["icc_profile_name"])

    def test_print_ppi_calculations(self) -> None:
        # A 2400 x 3000 photo (4:5 / 8x10 ratio, portrait)
        ppi_info = compute_effective_ppi(2400, 3000)
        eight_by_ten = next(item for item in ppi_info if item["target_name"] == "8x10")
        self.assertEqual(eight_by_ten["print_dimensions_in"], [8.0, 10.0])
        self.assertEqual(eight_by_ten["fill_ppi"], 300.0)
        self.assertEqual(eight_by_ten["fit_ppi"], 300.0)
        self.assertTrue(eight_by_ten["aspect_ratio_match"])
        self.assertFalse(eight_by_ten["crop_needed_for_borderless"])
        self.assertIn("Optimal", eight_by_ten["quality_tier"])

        # 11x14 target requires crop for 4:5 image
        eleven_fourteen = next(item for item in ppi_info if item["target_name"] == "11x14")
        self.assertTrue(eleven_fourteen["crop_needed_for_borderless"])

        # Custom requested target print size
        custom = compute_effective_ppi(
            1200, 1600, target_sizes=[{"name": "wallet", "w": 2.5, "h": 3.5}]
        )
        self.assertEqual(len(custom), 1)
        self.assertEqual(custom[0]["target_name"], "wallet")

    def test_preview_generation_and_source_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "large.png"
            Image.new("RGB", (2000, 1000), color=(100, 150, 200)).save(src)
            src_hash = sha256_file(src)

            preview_dst = root / "preview.png"
            with Image.open(src) as img:
                res = generate_preview(img, preview_dst, max_dimension=800)

            self.assertEqual(res["width"], 800)
            self.assertEqual(res["height"], 400)
            self.assertTrue(preview_dst.exists())
            # Confirm source was never altered
            self.assertEqual(sha256_file(src), src_hash)

    def test_native_crops_1_to_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "sample.png"
            # 800x600 image with distinct colored quadrants
            img = Image.new("RGB", (800, 600), "white")
            # put black mark in center
            img.putpixel((400, 300), (0, 0, 0))
            img.save(src)

            work = root / "crops_dir"
            work.mkdir()

            with Image.open(src) as loaded:
                crops = generate_native_crops(loaded, work, crop_size=128)

            # Default crops include center, top_left, top_right, bottom_left, bottom_right
            self.assertEqual(len(crops), 5)
            names = [c["name"] for c in crops]
            self.assertIn("center", names)
            self.assertIn("top_left", names)
            self.assertIn("bottom_right", names)

            for crop in crops:
                self.assertEqual(crop["width"], 128)
                self.assertEqual(crop["height"], 128)
                crop_path = Path(crop["path"])
                self.assertTrue(crop_path.exists())
                with Image.open(crop_path) as c_img:
                    self.assertEqual(c_img.size, (128, 128))

            # Center crop contains the mark at native relative coordinate (64, 64)
            center_crop = next(c for c in crops if c["name"] == "center")
            with Image.open(center_crop["path"]) as c_img:
                self.assertEqual(c_img.getpixel((64, 64)), (0, 0, 0))

    def test_custom_regions_cropping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "sample.png"
            Image.new("RGB", (400, 400), "gray").save(src)
            work = root / "custom_crops"
            work.mkdir()

            with Image.open(src) as loaded:
                crops = generate_native_crops(
                    loaded, work, regions=[[50, 60, 100, 80], [200, 250, 50, 50]]
                )

            self.assertEqual(len(crops), 2)
            self.assertEqual(crops[0]["box"], [50, 60, 100, 80])
            self.assertEqual(crops[0]["width"], 100)
            self.assertEqual(crops[0]["height"], 80)
            self.assertEqual(crops[1]["box"], [200, 250, 50, 50])

    def test_measured_clues_clipping_sharpness_noise(self) -> None:
        # All-white image: 100% highlight clipping, 0% shadow clipping
        white_img = Image.new("RGB", (100, 100), (255, 255, 255))
        white_clues = compute_measured_clues(white_img)
        self.assertEqual(white_clues["endpoint_clipping"]["highlight_clipped_percent"], 100.0)
        self.assertEqual(white_clues["endpoint_clipping"]["shadow_clipped_percent"], 0.0)
        self.assertEqual(white_clues["dynamic_range"]["max_luminance"], 255.0)

        # All-black image: 100% shadow clipping, 0% highlight clipping
        black_img = Image.new("RGB", (100, 100), (0, 0, 0))
        black_clues = compute_measured_clues(black_img)
        self.assertEqual(black_clues["endpoint_clipping"]["shadow_clipped_percent"], 100.0)
        self.assertEqual(black_clues["endpoint_clipping"]["highlight_clipped_percent"], 0.0)
        self.assertEqual(black_clues["dynamic_range"]["min_luminance"], 0.0)

        # High-frequency pattern vs smooth image
        sharp_img = Image.new("L", (100, 100), 128)
        for y in range(0, 100, 2):
            for x in range(0, 100, 2):
                sharp_img.putpixel((x, y), 255)
        smooth_img = Image.new("L", (100, 100), 128)

        sharp_clues = compute_measured_clues(sharp_img)
        smooth_clues = compute_measured_clues(smooth_img)
        self.assertGreater(sharp_clues["sharpness"]["score"], smooth_clues["sharpness"]["score"])
        self.assertGreater(sharp_clues["sharpness"]["score"], 500.0)
        self.assertEqual(smooth_clues["sharpness"]["score"], 0.0)

        # Explicit measurement limits must be included
        self.assertEqual(white_clues["measurement_limits"], MEASUREMENT_LIMITS)
        self.assertGreaterEqual(len(MEASUREMENT_LIMITS), 4)

    def test_prepare_inspection_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "family.png"
            work = root / "inspection_workspace"

            # Create test photo
            img = Image.new("RGB", (600, 800), (120, 140, 160))
            img.save(photo)
            initial_sha = sha256_file(photo)

            result = prepare_inspection(
                str(photo),
                working_dir=work,
                max_preview_dimension=400,
                crop_size=128,
            )

            self.assertTrue(result["valid"])
            self.assertTrue(result["exists"])
            self.assertEqual(result["source"]["orientation"], "portrait")
            self.assertEqual(result["source"]["width"], 600)
            self.assertEqual(result["source"]["height"], 800)
            self.assertEqual(result["source"]["sha256"], initial_sha)

            # Confirm artifacts were created in work dir
            artifacts = result["inspection_artifacts"]
            self.assertEqual(artifacts["working_dir"], str(work))
            preview_p = Path(artifacts["whole_photo_preview"]["path"])
            self.assertTrue(preview_p.exists())
            self.assertLessEqual(artifacts["whole_photo_preview"]["width"], 400)
            self.assertLessEqual(artifacts["whole_photo_preview"]["height"], 400)

            crops = artifacts["native_resolution_crops"]
            self.assertEqual(len(crops), 5)
            for c in crops:
                self.assertTrue(Path(c["path"]).exists())

            # Print resolution calculations
            print_ppi = result["print_resolution"]
            self.assertGreaterEqual(len(print_ppi), 3)

            # Measured clues
            self.assertIn("endpoint_clipping", result["measured_clues"])
            self.assertIn("measurement_limits", result["measured_clues"])

            # Verify source immutability
            self.assertEqual(sha256_file(photo), initial_sha)

    def test_prepare_inspection_missing_and_corrupt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "does_not_exist.png"
            res_missing = prepare_inspection(str(missing))
            self.assertFalse(res_missing["exists"])
            self.assertFalse(res_missing["valid"])
            self.assertIn("does not exist", res_missing["error"])

            corrupt = root / "corrupt.png"
            corrupt.write_bytes(b"NOT_A_PNG_FILE_HEADER")
            res_corrupt = prepare_inspection(str(corrupt))
            self.assertTrue(res_corrupt["exists"])
            self.assertFalse(res_corrupt["valid"])
            self.assertIn("Corrupt or unreadable", res_corrupt["error"])

    def test_cli_inspect_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img_p = root / "test.png"
            Image.new("RGB", (100, 100), "blue").save(img_p)
            work = root / "cli_work"

            args = argparse.Namespace(
                path=str(img_p),
                working_dir=str(work),
                preview_max=50,
                crop_size=30,
            )
            # Run _cmd_inspect with stdout suppressed
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                exit_code = _cmd_inspect(args)
            self.assertEqual(exit_code, 0)
            self.assertTrue(work.exists())
            self.assertTrue((work / "preview_test.png").exists())

    def test_cli_inspect_rejects_non_positive_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img_p = root / "test.png"
            Image.new("RGB", (64, 64), "blue").save(img_p)

            for preview_max, crop_size in [(0, 30), (50, -5)]:
                args = argparse.Namespace(
                    path=str(img_p),
                    working_dir=str(root / "work"),
                    preview_max=preview_max,
                    crop_size=crop_size,
                )
                buf = io.StringIO()
                with patch("sys.stdout", buf):
                    exit_code = _cmd_inspect(args)
                self.assertEqual(exit_code, 1)

    def test_shared_laplacian_and_preview_helpers(self) -> None:
        tiny = Image.new("L", (2, 2), 100)
        self.assertIsNone(compute_laplacian(tiny))
        self.assertEqual(compute_laplacian_variance(tiny), 0.0)

        sharp = Image.new("L", (32, 32), 100)
        for y in range(0, 32, 2):
            for x in range(0, 32, 2):
                sharp.putpixel((x, y), 240)
        lap_var = compute_laplacian_variance(sharp)
        clues = compute_measured_clues(sharp)
        self.assertEqual(round(lap_var, 2), clues["sharpness"]["score"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wide = Image.new("RGB", (400, 200), (10, 20, 30))
            p_inspect = root / "inspect_preview.png"
            p_review = root / "review_preview.png"
            inspect_res = generate_preview(wide, p_inspect, max_dimension=100)
            review_res = review.generate_preview(wide, p_review, max_dim=100)
            self.assertIsInstance(inspect_res, dict)
            self.assertIsInstance(review_res, tuple)
            self.assertEqual(review_res, (inspect_res["width"], inspect_res["height"]))
            self.assertEqual(review_res, (100, 50))
            self.assertEqual(review.generate_preview(wide, p_review, max_dim=0), (400, 200))


if __name__ == "__main__":
    unittest.main()
