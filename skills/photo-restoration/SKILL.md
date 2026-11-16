---
name: photo-restoration
description: Run checkpointed photo repairs and review each step.
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

# Photo Restoration

Restore damaged, faded, or soft photographs one verified recipe at a time using `artcraft_restore_step` and `artcraft_checkpoint`, saving 1:1 native and print-scale comparison crops after every step.

## When to Use

- Running one or more restoration recipes (`faded_tones`, `color_cast`, `dust_and_scratches`, `noise_and_grain`, `sharpening`, `enlargement`).
- Keeping step-by-step checkpoints (`manifest.json` and comparison crops) so any stage can be inspected or resumed.

## Prerequisites

- `photocraft-cli` installed and discoverable via `artcraft_status`.
- Source photograph inspected first with `photo-inspection` (`artcraft_prepare_inspection`).

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

1. Apply recipes in order as needed:
   - `faded_tones` (`recipe-faded-tones`) for washed-out tonal range.
   - `color_cast` (`recipe-color-cast`) to neutralize unwanted tints.
   - `dust_and_scratches` (`recipe-dust-scratches`) for localized dust and scratches.
   - `noise_and_grain` (`recipe-noise-grain`) to calm digital/scanner noise.
   - `sharpening` (`recipe-sharpening`) for mild edge crispness.
   - `enlargement` (`recipe-enlargement`) for proportional upscaling before print.
2. Run one recipe per `artcraft_restore_step` call, passing the previous step's `output_path` as the next step's `input_path`.
3. Inspect the generated 1:1 native crops, print-scale crops, and side-by-side comparison strips after each step.
4. Run `artcraft_build_review` when finished to verify that pixels actually changed, framing stayed intact (unless intended), and repaired areas did not collapse into blur.

## Pitfalls

- When `artcraft_restore_step` returns `status: "needs_decision"`, stop and ask the user before proceeding. It triggers automatically when `reconstruct_missing=true`, `content_type` indicates missing faces or lettering, or parameters exceed safe bounds (`in_black > 50`, `in_white < 200`, `gamma` outside `0.7..1.5`, `contrast > 40`, `midtones` shift beyond `+/-45`, `strength > 8` or `preserveDetails < 35`, sharpening `amount > 120` or `radius > 2.2`, or enlargement `scale > 4.0`).
- Never overwrite the original source photo or previous checkpoint outputs.

## Verification

- Confirm every step returns `status: "applied"`, unchanged `source_sha256`, a verified `output_sha256`, and readable before/after crops in `checkpoint_dir`.
