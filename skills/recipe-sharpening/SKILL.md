---
name: recipe-sharpening
description: Apply restrained unsharp masking without edge halos.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, restoration, sharpening, photography, photocraft]
    related_skills: [photo-restoration, photo-inspection, recipe-enlargement]
---

# Recipe: Sharpening Skill

Restore crisp edge acutance to mildly soft photographs or scans using `artcraft_restore_step` (`recipe="sharpening"`) or `artcraft_develop` while avoiding bright edge halos and film-grain amplification.

## When to Use

- Mild optical softness or scanner MTF loss where edge transitions need restrained crispness without ringing artifacts.

## Prerequisites

- `photocraft-cli` or `lightcraft-cli` discoverable via `artcraft_status`.
- Edge contrast and grain inspected via `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_restore_step`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/step_sharpened.png",
  "recipe": "sharpening",
  "parameters": {
    "amount": 50,
    "radius": 1.0,
    "threshold": 2
  },
  "checkpoint_dir": "<work_dir>/checkpoints",
  "step_name": "05_sharpening"
}
```

### LightCraft Alternative (`artcraft_develop`)

```bash
hermes artcraft develop <work_dir>/source/photo.png <work_dir>/work/step_sharpened.png \
  --set detail.sharpening=45 \
  --set detail.sharpenRadius=1.0 \
  --set detail.sharpenMasking=25
```

## Procedure

1. Set `amount` between `30` and `80` (default `50`, safe maximum `120`).
2. Set `radius` between `0.6` and `1.5` (default `1.0`, safe maximum `2.2`).
3. Set `threshold` between `1` and `6` (default `2`) so smooth sky and skin grain are not sharpened into texture noise.

## Pitfalls

- Stop and return `status: "needs_decision"` if `amount > 120`, `radius > 2.2`, if bright or dark halos appear along high-contrast boundaries, or if the image has severe out-of-focus blur.

## Verification

- Inspect 1:1 native crops along high-contrast edges and flat tonal areas in `checkpoint_dir` to confirm improved acutance with zero haloing.
