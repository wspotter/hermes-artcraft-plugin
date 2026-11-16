"""Tests for image inspection and post-edit pixel-diff verification."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from artcraft_plugin.verify import _count_changed_pixels, inspect_image, verify_edit


def _make_png(
    path: Path, size: tuple[int, int] = (32, 32), color: tuple[int, int, int] = (255, 255, 255)
) -> None:
    Image.new("RGB", size, color).save(path, format="PNG")


class TestVerify(unittest.TestCase):
    def test_inspect_valid_and_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "scan.png"
            _make_png(img_path, size=(40, 20))
            info = inspect_image(str(img_path))
            self.assertTrue(info["valid"])
            self.assertEqual(info["width"], 40)
            self.assertEqual(info["height"], 20)
            self.assertEqual(info["format"], "PNG")

            missing = inspect_image(str(Path(tmp) / "nope.png"))
            self.assertFalse(missing["exists"])

    def test_rejects_byte_identical_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "scan.png"
            out = Path(tmp) / "master.png"
            _make_png(src)
            _make_png(out)

            res = verify_edit(str(src), str(out))
            self.assertFalse(res["passed"])
            self.assertIn("no_op_edit", res["reason"])
            self.assertEqual(res["pixel_diff"]["changed_pixels"], 0)

    def test_accepts_changed_pixels_and_checks_region(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "scan.png"
            out = Path(tmp) / "master.png"
            _make_png(src, size=(32, 32))

            img = Image.open(src)
            img.putpixel((5, 5), (0, 0, 0))
            img.save(out, format="PNG")

            # Change is at (5, 5), inside [0, 0, 10, 10]
            ok_res = verify_edit(str(src), str(out), region=[0, 0, 10, 10])
            self.assertTrue(ok_res["passed"])
            self.assertEqual(ok_res["pixel_diff"]["changed_pixels"], 1)
            self.assertEqual(ok_res["pixel_diff"]["region"]["changed_pixels"], 1)

            # Outside [15, 15, 10, 10] -> should fail region check
            bad_reg = verify_edit(str(src), str(out), region=[15, 15, 10, 10])
            self.assertFalse(bad_reg["passed"])
            self.assertIn("no_op_in_region", bad_reg["reason"])

    def test_dimension_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "scan.png"
            out = Path(tmp) / "master.png"
            _make_png(src, size=(32, 32))
            _make_png(out, size=(64, 64))

            res = verify_edit(str(src), str(out), expected_width=32, expected_height=32)
            self.assertFalse(res["passed"])
            self.assertIn("dimension_mismatch", res["reason"])

    def test_corrupt_output_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "scan.png"
            out = Path(tmp) / "master.png"
            _make_png(src)
            out.write_bytes(b"not a png")

            res = verify_edit(str(src), str(out))
            self.assertFalse(res["passed"])
            self.assertIn("invalid_output", res["reason"])

    def test_count_changed_pixels_edge_cases(self) -> None:
        """_count_changed_pixels handles identical, alpha-only, and multi-channel diffs."""
        base_rgb = Image.new("RGB", (8, 8), (10, 20, 30))
        same_rgb = Image.new("RGB", (8, 8), (10, 20, 30))
        self.assertEqual(_count_changed_pixels(base_rgb, same_rgb), 0)

        base_rgba = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
        same_rgba = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
        self.assertEqual(_count_changed_pixels(base_rgba, same_rgba), 0)

        # Single-pixel alpha-only change
        alpha_diff = base_rgba.copy()
        alpha_diff.putpixel((3, 4), (10, 20, 30, 254))
        self.assertEqual(_count_changed_pixels(base_rgba, alpha_diff), 1)

        # Multi-channel diffs across distinct pixels
        multi_diff = base_rgba.copy()
        multi_diff.putpixel((0, 0), (11, 20, 30, 255))  # R changed
        multi_diff.putpixel((1, 0), (10, 25, 35, 255))  # G + B changed (still 1 pixel)
        multi_diff.putpixel((2, 0), (10, 20, 30, 128))  # A changed
        self.assertEqual(_count_changed_pixels(base_rgba, multi_diff), 3)

        # Cross-mode RGB vs RGBA where 2 pixels have non-255 alpha
        cross_rgba = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
        cross_rgba.putpixel((0, 1), (10, 20, 30, 200))
        cross_rgba.putpixel((7, 7), (99, 20, 30, 255))
        self.assertEqual(_count_changed_pixels(base_rgb, cross_rgba), 2)


if __name__ == "__main__":
    unittest.main()
