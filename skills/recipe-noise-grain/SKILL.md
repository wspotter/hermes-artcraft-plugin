---
name: recipe-noise-grain
description: Reduce sensor and scan noise while retaining fine detail.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, restoration, denoise, grain, photography]
    related_skills: [photo-restoration, photo-inspection, lightcraft-basics]
---

# Recipe: Noise and Grain

Calm digital chroma speckling and harsh scanner noise in smooth tonal regions using `artcraft_restore_step` (`recipe="noise_and_grain"`) or `artcraft_develop` while keeping facial texture, eyelashes, fabric weave, and lettering intact.

## When to Use

- Smooth areas (skies, walls, out-of-focus backdrops) show red/blue chroma blotches or harsh electronic noise rather than uniform film grain.

## Prerequisites

- `photocraft-cli` or `lightcraft-cli` discoverable via `artcraft_status`.
- Source noise and detail zones inspected via `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_restore_step`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/step_noise_grain.png",
  "recipe": "noise_and_grain",
  "parameters": {
    "strength": 4,
    "preserveDetails": 70,
    "reduceColorNoise": 45,
    "sharpenDetails": 15,
    "removeJpegArtifact": false
  },
  "checkpoint_dir": "<work_dir>/checkpoints",
  "step_name": "04_noise_grain"
}
```

### LightCraft Alternative (`artcraft_develop`)

```bash
hermes artcraft develop <work_dir>/source/photo.png <work_dir>/work/step_noise_grain.png \
  --set detail.nrLuminance=25 \
  --set detail.nrColor=40 \
  --set detail.nrDetail=60
```

## Procedure

1. Keep `strength` between `2` and `6` (default `4`, safe maximum `8`).
2. Keep `preserveDetails` between `50` and `85` (default `70`, safe minimum `35`).
3. Set `reduceColorNoise` between `25` and `65` (default `45`) and `sharpenDetails` between `10` and `25` (default `15`).

## Pitfalls

- `artcraft_restore_step` stops and returns `status: "needs_decision"` when `strength > 8` or `preserveDetails < 35`. Also pause and ask the user if denoising makes skin look waxy or blurs fine lettering.

## Verification

- Compare 1:1 native crops of smooth backgrounds and high-detail areas (eyes, text, fabric) in `checkpoint_dir`.
