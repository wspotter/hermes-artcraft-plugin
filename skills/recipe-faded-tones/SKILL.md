---
name: recipe-faded-tones
description: Restore compressed tonal range without clipping endpoints.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, restoration, levels, exposure, photography]
    related_skills: [photo-restoration, photo-inspection, lightcraft-basics]
---

# Recipe: Faded Tones Skill

Restore washed-out blacks, milky shadows, and compressed midtone contrast using `artcraft_restore_step` (`recipe="faded_tones"`) or `artcraft_develop` without crushing shadows or blowing out highlights.

## When to Use

- Inspection metrics from `artcraft_prepare_inspection` show elevated minimum luminance (`> 25`), lowered maximum luminance (`< 240`), and `0.0%` highlight/shadow clipping.

## Prerequisites

- `photocraft-cli` or `lightcraft-cli` discoverable via `artcraft_status`.
- Tonal endpoints inspected via `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_restore_step`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/step_faded_tones.png",
  "recipe": "faded_tones",
  "parameters": {
    "in_black": 12,
    "in_white": 242,
    "gamma": 1.05,
    "out_black": 0,
    "out_white": 255
  },
  "checkpoint_dir": "<work_dir>/checkpoints",
  "step_name": "01_faded_tones"
}
```

### LightCraft Alternative (`artcraft_develop`)

```bash
hermes artcraft develop <work_dir>/source/photo.png <work_dir>/work/step_faded_tones.png \
  --set light.contrast=15 \
  --set light.shadows=-10 \
  --set light.highlights=5
```

## Procedure

1. Set `in_black` between `5` and `30` (default `12`, safe maximum `50`).
2. Set `in_white` between `225` and `250` (default `242`, safe minimum `200`).
3. Set `gamma` between `0.90` and `1.15` (default `1.05`, safe range `0.7..1.5`).

## Pitfalls

- Stop and return `status: "needs_decision"` if `in_black > 50`, `in_white < 200`, or if the source already exhibits shadow or highlight clipping that would be worsened.

## Verification

- Inspect 1:1 native crops of deep shadows and bright highlights in `checkpoint_dir` to confirm subtle gradations remain distinct.
