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

# Print Preparation

Prepare print-ready files at exact physical dimensions and target PPI using `artcraft_prepare_print` (`hermes artcraft prep-print`). Stops before cropping mismatched aspect ratios, preserves 1:1 pixel proportions and ICC color profiles, and verifies the exported file from disk.

## When to Use

- Sizing a photo for physical print dimensions (`width_in`, `height_in`) at a target `ppi` (default `300`).
- Handling aspect-ratio differences between the source image and print sheet (`margins` vs `borderless`).

## Prerequisites

- Pillow installed in the plugin Python environment (`artcraft_status`).
- Source photo inspected via `artcraft_inspect` or `artcraft_prepare_inspection` so you know its resolution and effective PPI before exporting.

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

1. Calculate target pixel dimensions (`round(width_in * ppi)` by `round(height_in * ppi)`) and check `print_resolution` from `artcraft_prepare_inspection` first.
2. Handle aspect-ratio mismatches before writing:
   - `"margins"` (or `"fit"`) keeps the full photo centered with `margin_color` borders.
   - If the source and sheet aspect ratios differ and `fit_mode` is `"borderless"`, `"crop"`, or `"auto"` without `confirm_crop=true`, `artcraft_prepare_print` stops without writing an output file and returns `status: "needs_clarification"` with:
     *"Should the photo fill the [sheet] sheet with a [target_ratio] crop, or keep the [source_ratio] crop and add margins?"*
   - Only pass `confirm_crop=true` after the user explicitly confirms cropping.
3. Preserve proportions, color profiles, and print PPI:
   - Resizing uses Lanczos with 1:1 proportions (no stretching) and preserves embedded ICC profiles (or converts to `target_icc` / `"sRGB"`).
   - When `allow_upscale=false` (the default) and source dimensions or effective PPI fall below the target print size at `ppi`, `artcraft_prepare_print` returns an error (`{"ok": false, "error": ...}`) instead of quietly stretching pixels. Check PPI first, and ask the user whether to enlarge (`recipe-enlargement`), lower `ppi`, or retry with `allow_upscale=true`.

## Pitfalls

- Never pass `confirm_crop=true` on a mismatched aspect ratio unless the user explicitly asked for a borderless crop.
- Never enable `allow_upscale=true` without telling the user the effective source PPI will be below the target print PPI.
- For intentional manual crops, pass `crop_geometry` to `artcraft_build_review` (`hermes artcraft review --no-preserve-framing --crop-geometry ...`) to inspect the shaded trim overlay.

## Verification

- `artcraft_prepare_print` reopens `output_path` from disk and verifies exact pixel dimensions, file format, DPI metadata, `delivery_file.sha256`, `effective_source_ppi` vs `export_ppi`, ICC profile status, and `preview_path`.
