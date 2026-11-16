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

# PhotoCraft CLI Edits

Run localized PhotoCraft spot-healing strokes via `photocraft_spot_heal` with automatic pixel-diff checking inside and outside the target bounding box.

## When to Use

- Removing an isolated dust speck, blemish, or short scratch at known pixel coordinates.
- Enforcing zero pixel changes outside the allowed `[x, y, width, height]` region.

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

1. Inspect the source image and examine a 1:1 native crop around the blemish with `artcraft_prepare_inspection`.
2. Call `photocraft_spot_heal` with `input_path`, a new PNG `output_path` in an existing directory, integer stroke `points` inside `region`, brush `size` (`1..256`), and an allowed `region` `[x, y, width, height]` padded around every stroke point.
3. Check the returned JSON result and visually inspect the healed 1:1 crop before delivery.

## Pitfalls

- Pad `region` by at least `size` pixels around the stroke coordinates so brush feathering stays inside the allowed box.
- Never heal across eyes, lips, or critical lettering without asking the user first.

## Verification

- `photocraft_spot_heal` stages a copy of the source, checks `source_sha256` is unchanged, confirms `changed_pixels > 0` inside `region`, and checks `outside_pixels == 0` before writing `output_path`.
