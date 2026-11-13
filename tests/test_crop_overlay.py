import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from artcraft_plugin.tools import artcraft_build_review


class CropOverlayTests(unittest.TestCase):
    def test_review_distinguishes_equal_size_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.png", root / "output.png"
            Image.new("RGB", (100, 100), "white").save(source)
            Image.new("RGB", (60, 60), "white").save(output)
            args = dict(source_path=str(source), output_path=str(output),
                        working_dir=str(root), preserve_framing=False)

            def review(**geometry):
                return json.loads(artcraft_build_review(dict(args, crop_geometry=geometry)))

            retained = review(rect=[10, 10, 90, 90], artwork_rect=[10, 10, 90, 90], pixels_per_inch=40)
            trimmed = review(rect=[10, 10, 90, 70], artwork_rect=[10, 10, 90, 90], pixels_per_inch=40)
            self.assertEqual(retained["crop_review"]["paint_trim_inches"]["bottom"], 0)
            self.assertEqual(trimmed["crop_review"]["paint_trim_inches"]["bottom"], 0.5)
            with Image.open(retained["crop_review"]["comparison_path"]) as first:
                with Image.open(trimmed["crop_review"]["comparison_path"]) as second:
                    self.assertEqual(first.getpixel((66, 112)), (255, 255, 255))
                    self.assertLess(second.getpixel((66, 112))[0], 150)
            quad = review(quad=[[10, 10], [90, 20], [80, 90], [10, 80]])
            self.assertEqual(quad["crop_review"]["trim_status"], "unmeasured")
            self.assertFalse(review(quad=[[10, 10], [90, 90], [90, 10], [10, 90]])["ok"])
            self.assertFalse(review(rect=[0, 0, 101, 100])["ok"])
            self.assertEqual(json.loads(artcraft_build_review(args))["crop_review"]["status"], "not_supplied")
