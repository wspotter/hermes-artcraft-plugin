---
name: photocraft-cli-edits
description: Apply localized spot healing with pixel-diff verification.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, photocraft, spot-healing, retouching, verification]
    related_skills: [artcraft-router, photo-inspection, recipe-dust-scratches]
---

# PhotoCraft CLI Edits Skill

Run localized, non-destructive PhotoCraft spot-healing strokes via `photocraft_spot_heal` with automatic region-bounded pixel-diff verification.

## When to Use

- Removing an isolated dust speck, blemish, or short scratch at known pixel coordinates.
- Enforcing strict zero-pixel-change verification outside the allowed `[x, y, width, height]` bounding box.

## Prerequisites

- `photocraft-cli` installed and discoverable via `artcraft_status`.
- Source dimensions and defect coordinates identified via `artcraft_inspect` or `artcraft_prepare_inspection`.

## How to Run

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/photo_healed.png",
  "points": [[180, 240], [182, 290]],
  "size": 12,
  "region": [164, 224, 36, 84]
}
```

## Procedure

1. Inspect the source image and examine a 1:1 native-resolution crop of the blemish using `artcraft_prepare_inspection` or `artcraft_inspect`.
2. Call `photocraft_spot_heal` with `input_path`, a fresh PNG `output_path`, stroke `points` in source pixels, brush `size`, and an allowed `region` `[x, y, width, height]` padded to cover the brush radius around every stroke point.
3. Review the returned verification receipt and visually inspect the healed 1:1 crop before delivery.

## Pitfalls

- Pad `region` by at least `size` pixels on each side of the stroke coordinates so brush feathering does not spill outside the allowed region.
- Never heal across eyes, lips, or critical lettering without explicit operator confirmation.

## Verification

- `photocraft_spot_heal` stages a copy of the source, verifies `source_sha256` is unchanged, confirms `changed_pixels > 0` inside `region`, and enforces `outside_region_changed_pixels == 0` before publishing `output_path`.
