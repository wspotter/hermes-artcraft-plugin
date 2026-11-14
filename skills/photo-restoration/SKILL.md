---
name: photo-restoration
description: Run checkpointed photo repairs with visual review gates.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, restoration, photography, checkpoints, quality-control]
    related_skills:
      - artcraft-router
      - photo-inspection
      - recipe-faded-tones
      - recipe-color-cast
      - recipe-dust-scratches
      - recipe-noise-grain
      - recipe-sharpening
      - recipe-enlargement
---

# Photo Restoration Skill

Restore damaged, faded, or soft photographs through a non-destructive, checkpointed sequence of verified ArtCraft recipes (`artcraft_restore_step` and `artcraft_checkpoint`) with dual-scale before/after crops and an automated Stop/Ask gate.

## When to Use

- Applying one or more photographic restoration steps (`faded_tones`, `color_cast`, `dust_and_scratches`, `noise_and_grain`, `sharpening`, `enlargement`).
- Maintaining incremental checkpoints (`step_001_<recipe>`, `step_002_<recipe>`) with matching 1:1 native and print-scale comparison crops.

## Prerequisites

- `photocraft-cli` installed and discoverable via `artcraft_status`.
- Source photograph inspected first using `photo-inspection` (`artcraft_prepare_inspection`).

## How to Run

### 1. Apply a Restoration Step (`artcraft_restore_step`)

```json
{
  "input_path": "<work_dir>/source/photo.png",
  "output_path": "<work_dir>/work/step1_faded_tones.png",
  "recipe": "faded_tones",
  "parameters": {
    "in_black": 15,
    "in_white": 240,
    "gamma": 1.05
  },
  "checkpoint_dir": "<work_dir>/checkpoints",
  "step_name": "01_faded_tones",
  "target_print_ppi": 300
}
```

### 2. Inspect Checkpoints (`artcraft_checkpoint`)

```json
{
  "action": "list",
  "checkpoint_dir": "<work_dir>/checkpoints"
}
```

### 3. CLI Subcommands

```bash
hermes artcraft restore faded_tones <work_dir>/source/photo.png <work_dir>/work/step1_faded_tones.png \
  --params '{"in_black": 15, "in_white": 240}'

hermes artcraft checkpoint list <work_dir>/checkpoints
```

## Procedure

1. **Select recipes in order**:
   - `faded_tones` (`recipe-faded-tones`): Gentle levels adjustment preserving highlight and shadow detail.
   - `color_cast` (`recipe-color-cast`): Neutral color balance preserving natural skin warmth.
   - `dust_and_scratches` (`recipe-dust-scratches`): Localized spot healing or texture-safe dust filtering.
   - `noise_and_grain` (`recipe-noise-grain`): Selective noise reduction retaining facial detail and lettering.
   - `sharpening` (`recipe-sharpening`): Restrained unsharp mask avoiding edge halos.
   - `enlargement` (`recipe-enlargement`): Proportional upscaling paired with output sharpening.
2. **Execute incrementally**: Run one recipe per `artcraft_restore_step` call, passing the previous checkpoint output as the next `input_path`.
3. **Review dual-scale crops**: Inspect the generated 1:1 native crops, print-scale crops, and side-by-side comparison strip after each step.
4. **Build final review package**: Call `artcraft_build_review` to check for quality traps (no-op edits, unauthorized framing changes, or variance collapse >80% inside repaired areas).

## Pitfalls

- **Stop/Ask Gate (`status: "needs_decision"`)**: Stop immediately and ask the human operator before reconstructing missing faces, eyes, lettering, or large destroyed regions, or when parameters exceed safe bounds (`in_black > 50`, `in_white < 200`, sharpening `amount > 120` or `radius > 2.2`, upscaling `> 4x`).
- Never overwrite the original source image or prior checkpoint files.

## Verification

- Confirm every step returns `status: "completed"`, unchanged `source_sha256`, verified `output_sha256`, and readable before/after comparison crops in `checkpoint_dir`.
