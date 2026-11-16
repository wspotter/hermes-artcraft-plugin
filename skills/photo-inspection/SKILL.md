---
name: photo-inspection
description: Generate whole-photo previews, native crops, and metrics.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, inspection, photography, quality-control, crops]
    related_skills: [artcraft-router, photo-restoration, print-preparation]
---

# Photo Inspection

Inspect a photograph visually and metrically before editing, developing, or sizing it for print. Generates a downscaled whole-photo preview, 1:1 native crops, print PPI estimates, and tonal/sharpness/noise stats without touching the source file.

## When to Use

- Before any photo restoration, spot healing, tonal adjustment, or print preparation task.
- Deciding whether an image actually has defects or should be left untouched.

## Prerequisites

- Pillow installed in the plugin Python environment (`artcraft_status`).

## How to Run

### Hermes / MCP Tool (`artcraft_prepare_inspection`)

```json
{
  "path": "<work_dir>/source/photo.png",
  "working_dir": "<work_dir>/inspection",
  "crop_size": 256
}
```

### CLI Subcommand (`hermes artcraft inspect`)

```bash
hermes artcraft inspect <work_dir>/source/photo.png \
  --working-dir <work_dir>/inspection \
  --preview-max 1024 \
  --crop-size 256
```

## Procedure

1. Run `artcraft_prepare_inspection` to generate the whole-photo preview, 1:1 center and corner crops (plus any custom `regions`), image dimensions and ICC profile info, `print_resolution` estimates (8x10, 11x14, 5x7, 4x6, 16x20), and `measured_clues` (endpoint clipping, luminance range, Laplacian sharpness, smooth-patch noise).
2. Review five areas across the preview and 1:1 crops:
   - Faces and skin: separate real freckles, wrinkles, and beauty marks from dust or emulsion pits.
   - Lettering and fine textures: check edge crispness on signs, fabric weave, and architecture.
   - High-contrast edges: look for chromatic aberration, lens flare, or prior sharpening halos.
   - Smooth areas: check skies and backdrops for scratches, sensor dust, banding, or chroma blotches.
   - Corners and borders: check for vignetting, paper folds, tears, or scanner borders.
3. Separate real scene details from damage:

| Feature | Authentic Feature (Leave Untouched) | Actionable Defect (Record for Repair) |
|---|---|---|
| Linear marks | Wires, tree branches, seams, wrinkles following perspective | Scratches cutting across texture boundaries |
| Texture and grain | Uniform, luminance-coherent organic film grain | Chromatic blotches, hot pixels, JPEG blocks, scanner banding |
| Highlights | Catchlights in eyes, sun reflections, bright lamps, snow | Blown-out regions where expected detail clips at 255 |
| Shadows | Silhouettes, night scenes, dark clothing, deep contrast | Crushed shadows clipped at 0 from poor scanning |

4. Log each suspected defect with `issue_type`, `location` (`[x, y, width, height]` in source pixels), `confidence` (`high`, `medium`, `low`), and `recommended_action` (`leave_untouched`, `photocraft_spot_heal`, `tonal_correction`, or `clarify_with_user`).

## Pitfalls

- If no real defects exist, recommend leaving the photograph untouched rather than over-processing it.
- Note the `measurement_limits` returned in `measured_clues`: clipping stats cannot tell specular highlights or deep shadows apart from crushed detail, and sharpness scores drop naturally with shallow depth of field.
- If a defect crosses an eye, mouth, or critical lettering, do not guess. Record the coordinates and ask the user how to proceed.

## Verification

- Confirm `artcraft_prepare_inspection` returns `source.sha256` and valid file paths under `inspection_artifacts.whole_photo_preview.path` and `inspection_artifacts.native_resolution_crops`.
