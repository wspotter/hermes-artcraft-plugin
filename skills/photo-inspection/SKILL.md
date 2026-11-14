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

# Photo Inspection Skill

Inspect a photograph visually and metrically before applying any restoration, development, or print formatting. Generates a bounded whole-photo preview, 1:1 native-resolution crops, effective print PPI ratings, and measured tonal/sharpness clues without altering the source file.

## When to Use

- Before any photo restoration, spot healing, tonal adjustment, or print preparation task.
- Determining whether a photograph has genuine defects or should be left untouched.

## Prerequisites

- Pillow available in the plugin Python environment (`artcraft_status`).

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

1. **Generate inspection artifacts**: Call `artcraft_prepare_inspection` to produce:
   - **Whole-photo preview**: Bounded image for composition and overall tonal balance.
   - **Native-resolution crops (1:1 pixels)**: Center and corner crops (plus custom regions) without resampling.
   - **Dimensions & color profile**: Exact pixel dimensions, orientation, aspect ratio, and embedded ICC profile name.
   - **Effective print PPI**: Calculated PPI across standard sheet sizes (8×10, 11×14, 5×7, 4×6, 16×20).
   - **Measured clues**: Highlight/shadow clipping percentages, luminance dynamic range, sharpness score, and noise estimate.
2. **Examine five visual zones**:
   - **Faces and skin**: Distinguish authentic freckles, wrinkles, and beauty marks from emulsion pits or dust specks.
   - **Lettering and fine textures**: Check edge crispness on signs, fabric weave, and architectural details.
   - **High-contrast edges**: Check for chromatic aberration, optical flare, or prior sharpening halos.
   - **Smooth areas**: Inspect sky and backdrops for scratches, sensor dust, banding, or blotchy chroma noise.
   - **Corners and borders**: Check for vignetting, paper folds, emulsion tears, or scanner borders.
3. **Distinguish defects from authentic scene features**:

| Feature | Authentic Feature (Leave Untouched) | Actionable Defect (Record for Repair) |
|---|---|---|
| **Linear marks** | Wires, tree branches, seams, wrinkles following scene perspective. | Scratches cutting erratically across texture boundaries. |
| **Texture & grain** | Uniform, luminance-coherent organic film grain. | Chromatic blotches, hot pixels, JPEG blocks, or scanner banding. |
| **High highlights** | Catchlights in eyes, sun reflections, bright lamps, snow. | Blown-out highlights where expected texture is clipped at 255. |
| **Deep shadows** | Silhouettes, night scenes, dark suits, intentional chiaroscuro. | Crushed shadows where detail is clipped at 0 from bad scanning. |

4. **Record suspected issues**: Log each defect with `issue_type`, `location` (`[x, y, width, height]` in source pixels), `confidence` (`high`, `medium`, `low`), and `recommended_action` (`leave_untouched`, `photocraft_spot_heal`, `tonal_correction`, or `clarify_with_user`).

## Pitfalls

- If no actionable defects exist, recommend leaving the photograph untouched; unnecessary edits degrade authenticity.
- If a defect crosses an eye, mouth, or critical lettering, do not guess—record the coordinates and request operator clarification.

## Verification

- Confirm `artcraft_prepare_inspection` returns `source_sha256` alongside existing file paths for the preview image and all 1:1 native crops.
