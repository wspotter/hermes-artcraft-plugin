---
name: lightcraft-basics
description: Develop and render photos non-destructively.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, lightcraft, photography, raw-development, image-processing]
    related_skills: [artcraft-router, photo-inspection, lightcraft-cli-edits]
---

# LightCraft Basics

Develop and render photographs without altering source files using `artcraft_develop` (`lightcraft-cli render`). Each run writes to a fresh output path, checks that `source_sha256` is unchanged, and decodes the output image to confirm valid dimensions.

## When to Use

- Adjusting exposure, contrast, highlights, shadows, white balance, vibrance, or sharpening across a whole photograph.
- Applying a named LightCraft preset (`preset`) or exporting a resized web/review copy (`long_edge`, `quality`).
- Rendering RAW or raster inputs to PNG, JPEG, or TIFF without touching the original file.

## Prerequisites

- `lightcraft-cli` installed and discoverable via `artcraft_status`.
- Source image inspected first with `artcraft_inspect` or `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_develop`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/photo_developed.jpg",
  "sliders": {
    "light.exposure": 0.35,
    "light.contrast": 12,
    "light.highlights": -15,
    "light.shadows": 20,
    "color.temp": 5600,
    "color.vibrance": 10,
    "detail.sharpening": 35
  },
  "preset": "natural_warm",
  "long_edge": 2048,
  "quality": 92
}
```

### CLI Subcommand (`hermes artcraft develop`)

```bash
hermes artcraft develop <work_dir>/source/photo.png <work_dir>/work/photo_developed.jpg \
  --set light.exposure=0.35 \
  --set light.contrast=12 \
  --set color.temp=5600 \
  --set color.vibrance=10 \
  --set detail.sharpening=35 \
  --size 2048 \
  --quality 92
```

## Procedure

1. Run `artcraft_status` if CLI availability has not been checked in the current session.
2. Call `artcraft_inspect` or `artcraft_prepare_inspection` on `input_path` to check tonal clipping, resolution, and color profile.
3. Call `artcraft_develop` with a new `output_path` and restrained `sliders` (such as `light.exposure`, `light.contrast`, `color.temp`, `color.vibrance`, `detail.sharpening`), optional `preset`, `long_edge`, and `quality`.
4. Check the returned JSON (`source_sha256`, `output_sha256`, `width`, `height`, `format`) and inspect the rendered image visually before delivering.

## Pitfalls

- Never pass `output_path` equal to `input_path`; `artcraft_develop` rejects in-place overwrites.
- Avoid pushing exposure or contrast so far that highlights clip or shadow gradations collapse; check clipping stats after inspection.

## Verification

- `artcraft_develop` verifies that `source_sha256` matches before and after rendering and confirms the output decodes with non-zero `width` and `height`.
- For same-dimension raster exports, run `artcraft_verify_edit` or `artcraft_build_review` to compare before and after images.
