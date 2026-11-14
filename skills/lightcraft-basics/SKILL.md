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

# LightCraft Basics Skill

Develop and render photographs non-destructively with `artcraft_develop` (`lightcraft-cli render`). Every operation writes to a fresh output path, verifies that the source SHA-256 hash is unchanged, and decodes the rendered image to confirm valid dimensions.

## When to Use

- Adjusting exposure, contrast, highlights, shadows, white balance, vibrance, or sharpening across a whole photograph.
- Applying a named LightCraft preset (`--preset`) or exporting a resized web/review derivative (`long_edge`, `quality`).
- Rendering RAW or raster inputs to a clean PNG, JPEG, or TIFF deliverable without modifying the source file.

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

1. Run `artcraft_status` if CLI availability has not been verified in the current session.
2. Call `artcraft_inspect` or `artcraft_prepare_inspection` on `input_path` to check tonal clipping, resolution, and color profile.
3. Call `artcraft_develop` with a new `output_path` and restrained `sliders` (such as `light.exposure`, `light.contrast`, `color.temp`, `color.vibrance`, `detail.sharpening`), optional `preset`, `long_edge`, and `quality`.
4. Inspect the returned receipt (`source_sha256`, `output_sha256`, `width`, `height`, `format`) and review the rendered output visually before delivery.

## Pitfalls

- Never pass `output_path` equal to `input_path`; `artcraft_develop` refuses in-place overwrites to protect source integrity.
- Avoid extreme slider values that clip highlights or crush shadow gradations; inspect histograms and measured clues when adjusting exposure or contrast.

## Verification

- `artcraft_develop` automatically verifies that `source_sha256` is unchanged before and after execution and that the output image decodes cleanly with non-zero width and height.
- For same-dimension raster exports, run `artcraft_verify_edit` or `artcraft_build_review` to compare before and after images.
