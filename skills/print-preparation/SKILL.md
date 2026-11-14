---
name: print-preparation
description: Format print-ready images with aspect and PPI checks.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, printing, sizing, color-management, verification]
    related_skills: [artcraft-router, photo-inspection, recipe-enlargement]
---

# Print Preparation Skill

Prepare print-ready delivery files at exact physical dimensions and target PPI using `artcraft_prepare_print` (`hermes artcraft prep-print`). Enforces aspect-ratio clarification gates, preserves 1:1 pixel proportions and ICC color profiles, and verifies the exported file from disk.

## When to Use

- Formatting a photograph for physical printing at specific sheet dimensions (`width_in`, `height_in`) and resolution (`ppi`, default 300).
- Resolving aspect-ratio mismatches between the source image and target print sheet (`margins` vs `borderless` crop).

## Prerequisites

- Pillow available in the plugin Python environment (`artcraft_status`).
- Source photograph inspected via `artcraft_inspect` or `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_prepare_print`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/exports/print_8x10.png",
  "width_in": 8.0,
  "height_in": 10.0,
  "ppi": 300,
  "fit_mode": "margins",
  "margin_color": "white",
  "preserve_master_path": "<work_dir>/source/photo_master.png"
}
```

### CLI Subcommand (`hermes artcraft prep-print`)

```bash
hermes artcraft prep-print <work_dir>/source/photo.png <work_dir>/exports/print_8x10.png \
  --width 8.0 \
  --height 10.0 \
  --fit-mode margins \
  --ppi 300

hermes artcraft prep-print <work_dir>/source/photo.png <work_dir>/exports/print_8x10_crop.png \
  --width 8.0 \
  --height 10.0 \
  --fit-mode borderless \
  --confirm-crop \
  --ppi 300
```

## Procedure

1. **Calculate target dimensions**: Target pixel dimensions equal `round(width_in * ppi)` by `round(height_in * ppi)`.
2. **Enforce the Clarification Gate**:
   - When `fit_mode` is `"margins"` (or `"fit"`), the full photograph is preserved and centered with margins (`margin_color`).
   - When the source aspect ratio differs from the sheet ratio and `fit_mode` is `"borderless"` / `"crop"` or `"auto"` without `confirm_crop=true`, `artcraft_prepare_print` stops without writing an output file and returns `status: "needs_clarification"` with the question:
     *"Should the photo fill the [sheet] sheet with a [target_ratio] crop, or keep the [source_ratio] crop and add margins?"*
   - Only pass `confirm_crop=true` after the human operator confirms cropping.
3. **Preserve proportions and color profiles**:
   - Resizing uses Lanczos resampling with strict 1:1 pixel aspect ratio (never stretch).
   - Embedded ICC profiles (sRGB, Display P3, Adobe RGB) are retained in the exported deliverable.
   - Check `effective_source_ppi` vs `export_ppi`; if `effective_source_ppi < ppi` and `allow_upscale=false`, pause for confirmation.

## Pitfalls

- Never pass `confirm_crop=true` on a mismatched aspect ratio unless the user explicitly chose a borderless crop.
- For intentional manual crops, pass `crop_geometry` to `artcraft_build_review` (`hermes artcraft review --no-preserve-framing --crop-geometry ...`) to review the shaded trim boundary.

## Verification

- `artcraft_prepare_print` reopens and decodes `output_path` from disk, confirming target pixel width and height, file format, DPI metadata, embedded ICC profile presence, unchanged `source_sha256`, and a visual composition preview.
