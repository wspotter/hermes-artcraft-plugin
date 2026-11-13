"""Render editor-supplied crop geometry for visual review."""

import math

from PIL import Image, ImageDraw


def _numbers(values, count):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError(f"Expected {count} numeric coordinates")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("Crop coordinates must be finite numbers")
    return tuple(values)


def _rectangle(values, width, height):
    left, top, right, bottom = _numbers(values, 4)
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("Crop rectangle must be nonempty and within the source")
    return left, top, right, bottom


def validate_crop(geometry, width, height):
    if geometry is None:
        return {"status": "not_supplied", "trim_status": "unmeasured"}
    if not isinstance(geometry, dict) or ("rect" in geometry) == ("quad" in geometry):
        raise ValueError("Supply exactly one crop rect or quad")
    trim = None
    if "rect" in geometry:
        left, top, right, bottom = _rectangle(geometry["rect"], width, height)
        points = [(left, top), (right, top), (right, bottom), (left, bottom)]
        if "artwork_rect" in geometry and "pixels_per_inch" in geometry:
            al, at, ar, ab = _rectangle(geometry["artwork_rect"], width, height)
            ppi, = _numbers([geometry["pixels_per_inch"]], 1)
            if ppi <= 0:
                raise ValueError("pixels_per_inch must be positive")
            if min(right, ar) <= max(left, al) or min(bottom, ab) <= max(top, at):
                raise ValueError("Crop must overlap the calibrated artwork rectangle")
            trim = {
                edge: max(0, distance) / ppi
                for edge, distance in zip(
                    ("left", "top", "right", "bottom"),
                    (left - al, top - at, ar - right, ab - bottom),
                )
            }
            if not all(math.isfinite(value) for value in trim.values()):
                raise ValueError("Calibrated trim must be finite")
    else:
        quad = geometry["quad"]
        if not isinstance(quad, (list, tuple)) or len(quad) != 4:
            raise ValueError("Crop quad must have four perimeter points")
        points = [_numbers(point, 2) for point in quad]
        if any(not (0 <= x <= width and 0 <= y <= height) for x, y in points):
            raise ValueError("Crop quad must be within the source")
        turns = []
        for index in range(4):
            a, b, c = (points[(index + offset) % 4] for offset in range(3))
            turns.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
        if not (all(turn > 0 for turn in turns) or all(turn < 0 for turn in turns)):
            raise ValueError("Crop quad must be strictly convex and ordered around its perimeter")
    return {
        "status": "editor_supplied",
        "retained_source_pixels": points,
        "trim_status": "measured_from_supplied_scale" if trim is not None else "unmeasured",
        "paint_trim_inches": trim,
    }


def render_crop_overlay(source_preview, output_preview, dimensions, points, path):
    with Image.open(source_preview) as image:
        source = image.convert("RGB")
    with Image.open(output_preview) as image:
        output = image.convert("RGB")
    width, height = dimensions
    polygon = [(x * source.width / width, y * source.height / height) for x, y in points]
    mask = Image.new("L", source.size, 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    shaded = Image.blend(source, Image.new("RGB", source.size, "#131a22"), 0.58)
    shaded.paste(source, mask=mask)
    ImageDraw.Draw(shaded).line(polygon + polygon[:1], fill="#ffdf42", width=3)
    gap, header = 16, 32
    sheet = Image.new("RGB", (source.width + output.width + gap * 3, max(source.height, output.height) + header + gap), "#20262d")
    sheet.paste(shaded, (gap, header))
    sheet.paste(output, (source.width + 2 * gap, header))
    draw = ImageDraw.Draw(sheet)
    draw.text((gap, 8), "Source / retained outline", fill="white")
    draw.text((source.width + 2 * gap, 8), "Output", fill="white")
    sheet.save(path)
