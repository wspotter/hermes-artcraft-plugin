---
name: recipe-color-cast
description: Remove unwanted color tints while preserving skin tones.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, restoration, color-balance, photography, photocraft]
    related_skills: [photo-restoration, photo-inspection, lightcraft-basics]
---

# Recipe: Color Cast

Neutralize unwanted overall color tints (yellowed paper, green fluorescent cast, or cyan dye shift) using `artcraft_restore_step` (`recipe="color_cast"`) or `artcraft_develop` while keeping skin tones and luminosity natural.

## When to Use

- Neutral gray areas (white collars, concrete, gray backdrops) show an obvious RGB channel tint.
- The color shift comes from aging, dye fading, or mixed lighting rather than intentional golden-hour warmth or sepia toning.

## Prerequisites

- `photocraft-cli` or `lightcraft-cli` discoverable via `artcraft_status`.
- Source inspected with `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_restore_step`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/step_color_cast.png",
  "recipe": "color_cast",
  "parameters": {
    "midtones": [0, 0, 15],
    "preserveLuminosity": true
  },
  "checkpoint_dir": "<work_dir>/checkpoints",
  "step_name": "02_color_cast"
}
```

### LightCraft Alternative (`artcraft_develop`)

```bash
hermes artcraft develop <work_dir>/source/photo.png <work_dir>/work/step_color_cast.png \
  --set color.temp=5600 \
  --set color.tint=0
```

## Procedure

1. Keep `midtones` `[cyan_red, magenta_green, yellow_blue]` within `-25` to `+25` for typical shifts (safe maximum absolute shift: `45`).
2. Keep `preserveLuminosity: true` so correcting color balance does not darken shadows or clip highlights.
3. Keep `shadows` and `highlights` at `[0, 0, 0]` unless mild counter-balancing (`-15` to `+15`) is needed.

## Pitfalls

- `artcraft_restore_step` stops and returns `status: "needs_decision"` automatically if any `midtones` shift exceeds `+/-45`.
- Pause and ask the user if skin tones shift toward chalky gray, green, or purple, or if the image appears to have intentional sepia toning.

## Verification

- Inspect 1:1 native crops of skin tones and neutral grays alongside print-scale comparison crops in `checkpoint_dir`.
