---
name: artcraft-router
description: Route creative media tasks across the ArtCraft CLI suite.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, router, photocraft, lightcraft, filmcraft, soundcraft]
    related_skills:
      - photo-inspection
      - photocraft-cli-edits
      - lightcraft-basics
      - lightcraft-cli-edits
      - soundcraft-basics
      - filmcraft-basics
      - print-preparation
      - photo-restoration
      - recipe-maker
---

# ArtCraft Router Skill

Route image, photo development, audio, video, restoration, and print-preparation tasks across all four ArtCraft applications (`PhotoCraft`, `LightCraft`, `FilmCraft`, `SoundCraft`) using non-destructive tools and post-edit verification.

## When to Use

- Starting any creative media inspection, editing, restoration, development, print formatting, audio conversion, or video export task.
- Selecting the right ArtCraft tool among the 15 Hermes tools / 13 unified MCP tools.

## Prerequisites

- ArtCraft CLI suite (`photocraft-cli`, `lightcraft-cli`, `filmcraft-cli`, `soundcraft-cli`) discoverable via `artcraft_status`.

## How to Run

Check installed binaries first if not yet verified in the current session:

```bash
hermes artcraft doctor
```

Or call `artcraft_status` via tool invocation.

## Procedure

1. **Check availability**: Call `artcraft_status` (or `photocraft_run` / `lightcraft_run` for CLI flag checks) to confirm which ArtCraft binaries are installed.
2. **Inspect photographs first**: Load `photo-inspection`. Use `artcraft_prepare_inspection` for whole-photo previews, 1:1 native crops, print PPI ratings, and measured clues, or `artcraft_inspect` for quick metadata and SHA-256 checks.
3. **Heal localized blemishes (`PhotoCraft`)**: Load `photocraft-cli-edits` and call `photocraft_spot_heal` with an explicit bounding `region` `[x, y, width, height]`.
4. **Develop & tone photographs (`LightCraft`)**: Load `lightcraft-basics` and call `artcraft_develop` (`hermes artcraft develop`) with non-destructive `sliders`, `preset`, `long_edge`, and `quality`.
5. **Inspect & convert audio (`SoundCraft`)**: Load `soundcraft-basics` and call `artcraft_audio_basic` (`hermes artcraft audio`) with `action="info"` or `action="convert"` (`sample_rate`, `bit_depth`, `normalize`, `dither`).
6. **Probe, frame-grab & export video (`FilmCraft`)**: Load `filmcraft-basics` and call `artcraft_video_basic` (`hermes artcraft video`) with `action="probe"`, `action="render_frame"`, or `action="export"`.
7. **Prepare print deliverables**: Load `print-preparation` and call `artcraft_prepare_print` (`hermes artcraft prep-print`) to enforce aspect-ratio clarification gates, target PPI, and color profile preservation.
8. **Run checkpointed photo restoration**: Load `photo-restoration` (and recipe skills `recipe-faded-tones`, `recipe-color-cast`, `recipe-dust-scratches`, `recipe-noise-grain`, `recipe-sharpening`, `recipe-enlargement`). Use `artcraft_restore_step` and `artcraft_checkpoint`, honoring `status: "needs_decision"` Stop/Ask gates.
9. **Build reviews & manage jobs**: Use `artcraft_build_review` (`hermes artcraft review`) for quality-trap detection and before/after crop packages, `artcraft_verify_edit` (`hermes artcraft verify`) for pixel-diff bounds checks, and `artcraft_job` (`hermes artcraft job`) for deterministic job folders and delivery receipt reconciliation.
10. **Author new reusable recipes**: Load `recipe-maker` when capturing, prototyping, verifying, and saving a new custom ArtCraft workflow skill (`skills/recipe-<slug>/SKILL.md`).

## Pitfalls

- Never mutate source media in-place; every editing tool requires a distinct `output_path` and verifies `source_sha256`.
- Never bypass `status: "needs_clarification"` (print aspect-ratio gate) or `status: "needs_decision"` (restoration Stop/Ask gate) without human confirmation.

## Verification

- Every write operation returns `source_sha256` and `output_sha256` alongside decoded format/stream verification.
- Visually inspect generated previews and 1:1 native crops before final delivery.
