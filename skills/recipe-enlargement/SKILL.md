---
name: recipe-enlargement
description: Upscale images proportionally with restrained sharpening.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, restoration, enlargement, upscaling, printing]
    related_skills: [photo-restoration, print-preparation, recipe-sharpening]
---

# Recipe: Enlargement Skill

Upscale low-resolution photographs proportionally with detail-preserving interpolation and restrained output sharpening using `artcraft_restore_step` (`recipe="enlargement"`).

## When to Use

- Effective source resolution (`effective_source_ppi`) is below the target print resolution (for example, 100 PPI instead of 300 PPI at the requested print size).

## Prerequisites

- `photocraft-cli` discoverable via `artcraft_status`.
- Target print dimensions and source resolution verified via `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_restore_step`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/step_enlarged.png",
  "recipe": "enlargement",
  "parameters": {
    "width": 2400,
    "height": 3000,
    "resample": "preserveDetails",
    "sharpen_amount": 40,
    "sharpen_radius": 0.8,
    "sharpen_threshold": 1
  },
  "checkpoint_dir": "<work_dir>/checkpoints",
  "step_name": "06_enlargement"
}
```

## Procedure

1. Compute target `width` and `height` at the exact source aspect ratio (within 0.1%) using scale factors between `1.1x` and `3.0x` (safe maximum `4.0x`).
2. Use `resample: "preserveDetails"` (or `"bicubicSmoother"`) paired with restrained output sharpening (`amount` `30..50`, `radius` `0.6..1.0`, `threshold` `1`).
3. Inspect both 1:1 native crops and simulated print-scale crops to confirm clean edge transitions.

## Pitfalls

- Stop and return `status: "needs_decision"` if the requested scale factor exceeds `4.0x` or if target dimensions would alter the source aspect ratio.
- Never use generative super-resolution that hallucinates synthetic facial details or fictional text.

## Verification

- Verify `output_path` decodes to the exact target `width` and `height`, preserves source aspect ratio, and passes `artcraft_build_review`.
