---
name: photo-restoration
description: Systematic, non-destructive photographic restoration recipes with incremental checkpointing, before/after crop comparisons, and a Stop/Ask gate for missing content.
---

# Photo Restoration

A non-destructive, recipe-driven workflow for restoring damaged, faded, or soft photographs using verified ArtCraft CLI operations.

## Core Principles

1. **Non-Destructive & Sequential**: Every operation reads an immutable source or prior checkpoint and writes a fresh output file. The original photograph is never overwritten.
2. **Incremental Checkpointing**: Save a verified checkpoint after each meaningful change (`step_001_<recipe>`, `step_002_<recipe>`). Work can be resumed from any prior checkpoint.
3. **Dual-Scale Visual Inspection**: Every checkpoint generates matching 1:1 native-resolution and print-scale before/after crops, along with side-by-side comparison strips.
4. **Stop/Ask Gate**: If a repair involves reconstructing missing facial identity, lettering, or important missing content, or if requested parameters exceed safe bounds, stop immediately and return `status: "needs_decision"`. Never invent or hallucinate missing features without explicit human decision.

## Restoration Recipes

| Recipe | Action | Acceptance Check | CLI Command |
|---|---|---|---|
| **Faded tones** | Gentle tonal correction | Preserves highlight & shadow detail without crushing | `photocraft-cli run ... --cmd image.adjustments.levels` |
| **Color cast** | Neutral balance & color adjustment | Preserves believable skin tones & natural warmth | `photocraft-cli run ... --cmd image.adjustments.colorBalance` |
| **Dust & scratches** | Localized healing or texture-safe filtering | Preserves nearby edges; 0 changed pixels outside region | `photocraft-cli run ... --cmd paint.spotHealing` |
| **Noise & grain** | Selective noise reduction | Retains facial detail, lettering, and authentic texture | `photocraft-cli run ... --cmd filter.noise.reduceNoise` |
| **Sharpening** | Restrained unsharp mask | Avoids edge halos and noise amplification | `photocraft-cli run ... --cmd filter.sharpen.unsharpMask` |
| **Enlargement** | Proportional upscaling + output sharpening | Preserves composition, aspect ratio, and fine details | `photocraft-cli run ... --cmd image.imageSize ... --cmd filter.sharpen.unsharpMask` |

## Tool Usage

### 1. Apply a Restoration Step
```json
{
  "name": "artcraft_restore_step",
  "arguments": {
    "input_path": "/path/to/source.png",
    "output_path": "/path/to/work/step1_faded_tones.png",
    "recipe": "faded_tones",
    "parameters": {
      "in_black": 15,
      "in_white": 240,
      "gamma": 1.05
    },
    "checkpoint_dir": "/path/to/work/checkpoints",
    "step_name": "01_faded_tones",
    "target_print_ppi": 300
  }
}
```

### 2. Inspect Checkpoints
```json
{
  "name": "artcraft_checkpoint",
  "arguments": {
    "action": "list",
    "checkpoint_dir": "/path/to/work/checkpoints"
  }
}
```

### 3. CLI Invocations
```bash
# Run a restoration step
hermes artcraft restore faded_tones input.png output.png --params '{"in_black": 15, "in_white": 240}'

# Trigger Stop/Ask gate on missing content
hermes artcraft restore dust_and_scratches input.png output.png --content-type missing_face

# List checkpoints
hermes artcraft checkpoint list /path/to/work/checkpoints
```

## Unsupported Operations

The following operations are outside safe photographic restoration and will trigger `status: "needs_decision"`:
- Reconstructing missing faces, facial features, or missing person identity.
- Reconstructing missing lettering, street names, or text.
- Generative diffusion inpainting / hallucination of destroyed image portions.
- Extreme sharpening amounts (> 120) or radii (> 2.2) creating bright halos.
- Crushing shadows (`in_black` > 50) or blowing highlights (`in_white` < 200).
- Extreme upscaling scales (> 4x) without human operator instruction.
