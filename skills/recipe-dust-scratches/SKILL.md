---
name: recipe-dust-scratches
description: Heal isolated dust specks and scratches without blurring.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, restoration, spot-healing, retouching, photocraft]
    related_skills: [photo-restoration, photocraft-cli-edits, photo-inspection]
---

# Recipe: Dust and Scratches Skill

Remove isolated dust specks, hairs, and emulsion scratches using localized `photocraft_spot_heal` or `artcraft_restore_step` (`recipe="dust_and_scratches"`) while preserving surrounding grain and edge acutance.

## When to Use

- High-contrast, sharp-edged blemishes or scratches that cut across natural texture boundaries.
- Defects located away from critical facial identity features or fine lettering.

## Prerequisites

- `photocraft-cli` discoverable via `artcraft_status`.
- Defect coordinates and bounding `region` `[x, y, width, height]` measured via `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_restore_step`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/step_dust_scratches.png",
  "recipe": "dust_and_scratches",
  "parameters": {
    "points": [[180, 240], [182, 290]],
    "size": 10
  },
  "region": [165, 225, 35, 80],
  "checkpoint_dir": "<work_dir>/checkpoints",
  "step_name": "03_dust_scratches"
}
```

## Procedure

1. Verify that the mark is an actual scratch or dust speck rather than an authentic scene feature (wires, branches, seams, whiskers, or wrinkles).
2. Prefer localized spot healing (`photocraft_spot_heal` or `artcraft_restore_step` with `points`, `size` `4..24` px, and tight `region`).
3. For dense area dust only, use filter parameters `radius` `1..2` (safe max `3`) and `threshold` `10..40` so subtle grain and edges are not blurred.

## Pitfalls

- Stop and return `status: "needs_decision"` if the defect crosses eyes, pupils, lips, teeth, or important lettering, or if the damaged area is too large for patch blending without inventing content.
- Avoid smeared repairs: `artcraft_build_review` flags repairs where interior pixel variance collapses by more than 80%.

## Verification

- Confirm zero changed pixels outside `region` (`outside_region_changed_pixels == 0`) and inspect 1:1 native crops to verify surrounding texture remains sharp.
