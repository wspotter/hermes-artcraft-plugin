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

# Recipe: Color Cast Skill

Neutralize unwanted overall color tints (yellow aged paper, green fluorescent cast, or cyan dye fading) using `artcraft_restore_step` (`recipe="color_cast"`) or `artcraft_develop` while preserving natural skin warmth and luminosity.

## When to Use

- Neutral gray elements (white collars, concrete, neutral backdrops) show a measurable chromatic imbalance across red, green, and blue channels.
- The tint is technical degradation rather than intentional golden-hour lighting or deliberate sepia toning.

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
2. Keep `preserveLuminosity: true` to prevent darkening or blowing out tonal values.
3. Keep `shadows` and `highlights` at `[0, 0, 0]` unless subtle counter-balancing (`-15` to `+15`) is required.

## Pitfalls

- Stop and return `status: "needs_decision"` if a channel shift `> 45` is requested, if skin tones shift toward chalky gray, green, or purple, or if the photograph has intentional artistic sepia toning.

## Verification

- Inspect 1:1 native crops of skin tones and known neutral references alongside print-scale comparison crops in `checkpoint_dir`.
