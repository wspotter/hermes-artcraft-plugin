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

# Recipe: Enlargement

Upscale low-resolution photographs proportionally with detail-preserving resampling and mild output sharpening using `artcraft_restore_step` (`recipe="enlargement"`).

## When to Use

- Effective source resolution (`effective_source_ppi`) is below the target print resolution (for example, 100 PPI instead of 300 PPI at the requested sheet size).

## Prerequisites

- `photocraft-cli` discoverable via `artcraft_status`.
- Target print size and source dimensions checked via `artcraft_prepare_inspection`.

## How to Run

### Hermes / MCP Tool (`artcraft_restore_step`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/step_enlarged.png",
  "recipe": "enlargement",
  "parameters": {
    "scale": 2.0,
    "resample": "preserveDetails",
    "sharpen_amount": 40,
    "sharpen_radius": 0.8
  },
  "checkpoint_dir": "<work_dir>/checkpoints",
  "step_name": "06_enlargement"
}
```

Note: You can pass `scale` (checked against the `> 4.0x` guard) or explicit `width` / `height` pixels.

## Procedure

1. Choose a proportional `scale` between `1.1` and `3.0` (safe maximum `4.0`), or compute `width` and `height` matching the exact source aspect ratio.
2. Use `resample: "preserveDetails"` (or `"bicubicSmoother"`) with restrained output sharpening (`sharpen_amount` `30..50`, `sharpen_radius` `0.6..1.0`).
3. Inspect both 1:1 native crops and print-scale crops in `checkpoint_dir` to check edge smoothness and noise.

## Pitfalls

- `artcraft_restore_step` stops and returns `status: "needs_decision"` if `parameters.scale > 4.0`. Also stop and check with the user if target dimensions would stretch the aspect ratio.
- Never use generative upscaling that invents facial features or fictional lettering.

## Verification

- Confirm `output_path` decodes to the expected `width` and `height`, preserves source proportions, and passes `artcraft_build_review` (`--no-preserve-framing` is not needed when aspect ratio stays identical).
