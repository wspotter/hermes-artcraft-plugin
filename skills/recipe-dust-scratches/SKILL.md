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

# Recipe: Dust and Scratches

Remove isolated dust specks, hairs, and emulsion scratches using localized `photocraft_spot_heal` or `artcraft_restore_step` (`recipe="dust_and_scratches"`) while keeping surrounding film grain and sharp edges intact.

## When to Use

- Sharp, high-contrast specks or scratches that cut across natural scene textures.
- Defects located away from critical facial features or fine lettering.

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

1. Confirm the mark is actually dust or a scratch rather than part of the scene (wires, tree branches, seams, whiskers, or wrinkles).
2. Prefer localized spot healing (`photocraft_spot_heal` or `artcraft_restore_step` with `points`, `size` `4..24` px, and a tight `region`).
3. Only for widespread fine dust, omit `points`/`region` to run the filter path with `radius` `1..2` (safe max `3`) and `threshold` `10..40` so grain and edges stay crisp.

## Pitfalls

- Stop and ask the user (or pass `reconstruct_missing=true` / `content_type="missing_face"` so `artcraft_restore_step` returns `status: "needs_decision"`) if a defect crosses eyes, pupils, lips, teeth, or important lettering, or if the damaged gap is too large to patch cleanly.
- Avoid smeared patches: `artcraft_build_review` flags repairs where interior texture collapses (`>= 80%` Laplacian drop or `>= 85%` variance drop).

## Verification

- `photocraft_spot_heal` (and `artcraft_restore_step` when passed both `points` and `region`) verifies `outside_pixels == 0` and rejects edits that alter pixels outside `region`.
- Inspect 1:1 native crops in `checkpoint_dir` to confirm surrounding grain and edges stayed sharp.
