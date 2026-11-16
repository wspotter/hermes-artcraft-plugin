---
name: artcraft-router
description: Route photo, video, and audio jobs cleanly.
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
      - recipe-film-matte
      - recipe-voice-master
      - recipe-web-clip
      - recipe-maker
---

# ArtCraft Router

Route photo, audio, video, restoration, and print tasks across PhotoCraft, LightCraft, FilmCraft, and SoundCraft without modifying source files.

## When to Use

- Starting any creative media inspection, edit, restoration, print prep, audio conversion, or video export task.
- Picking the right tool among the 16 Hermes tools (14 exposed over stdio MCP).

## Prerequisites

- ArtCraft CLIs (`photocraft-cli`, `lightcraft-cli`, `filmcraft-cli`, `soundcraft-cli`) discoverable via `artcraft_status`.

## How to Run

Check installed binaries first if they have not been checked in the current session:

```bash
hermes artcraft doctor
```

Or call `artcraft_status`.

## Procedure

1. Confirm available binaries with `artcraft_status` (or `photocraft_run` / `lightcraft_run` with `["--help"]` or `["--version"]` to check CLI flags).
2. Inspect photos before editing by loading `photo-inspection` (`artcraft_prepare_inspection` for previews, 1:1 native crops, print PPI, and tonal/sharpness/noise stats, or `artcraft_inspect` for quick metadata).
3. Load the matching workflow skill for the requested task:

| Task | Skill to load | Primary tool / CLI |
|---|---|---|
| Localized blemish or scratch removal | `photocraft-cli-edits` | `photocraft_spot_heal` |
| Photo development, presets, resize | `lightcraft-basics` | `artcraft_develop` / `hermes artcraft develop` |
| LightCraft CLI flag check & export diff | `lightcraft-cli-edits` | `lightcraft_run`, `artcraft_verify_edit` |
| Audio probe, resample, normalize | `soundcraft-basics` | `artcraft_audio_basic` / `hermes artcraft audio` |
| Video probe, frame grab, trim/export | `filmcraft-basics` | `artcraft_video_basic` / `hermes artcraft video` |
| Physical print sizing & margins | `print-preparation` | `artcraft_prepare_print` / `hermes artcraft prep-print` |
| Multi-step photo restoration | `photo-restoration` + `recipe-*` | `artcraft_restore_step`, `artcraft_recipe` |
| Portable LightCraft / SoundCraft / FilmCraft looks | `recipe-film-matte`, `recipe-voice-master`, `recipe-web-clip` | `artcraft_recipe` / `hermes artcraft recipe run` |
| Create, validate, export, or import a recipe | `recipe-maker` | `artcraft_recipe` / `hermes artcraft recipe` |

4. Before handing off final image edits, run `artcraft_build_review` (`hermes artcraft review`) to generate before/after crops and check for no-ops, unexpected aspect shifts, or blurred patches. Use `artcraft_job` (`hermes artcraft job`) to keep multi-stage work organized in `source/`, `work/`, `previews/`, and `exports/` and to track deliveries.

## Pitfalls

- Never pass an `output_path` that matches `input_path`. Every write tool requires a new output path and checks the source SHA-256 hash.
- Never bypass `status: "needs_clarification"` (print aspect mismatch) or `status: "needs_decision"` (restoration safety bounds or missing-content reconstruction) without explicit user approval.

## Verification

- Every write operation returns SHA-256 hashes alongside decoded image dimensions or probed media metadata.
- Visually inspect generated previews and 1:1 native crops before delivering final files.
