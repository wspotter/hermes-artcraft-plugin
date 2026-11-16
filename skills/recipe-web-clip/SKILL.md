---
name: recipe-web-clip
description: Probe, preview, and export web-ready video clips.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, recipe, filmcraft, video, export]
    related_skills: [filmcraft-basics, soundcraft-basics, recipe-maker]
---

# Recipe: Web Clip

Probe a video clip, extract a PNG inspection frame into `<work_dir>`, and export an H.264 clip with optional trim timestamps via `filmcraft-cli`.

## When to Use

- Preparing consistent social or web preview MP4 exports without touching source footage.

## Prerequisites

- `filmcraft-cli` discoverable via `artcraft_status`.

## How to Run

```bash
hermes artcraft recipe run recipe-web-clip <work_dir>/source/clip.mp4 <work_dir>/exports/clip_web.mp4
```

Trim a specific segment:

```bash
hermes artcraft recipe run recipe-web-clip <work_dir>/source/clip.mp4 <work_dir>/exports/clip_web.mp4 \
  --param start_seconds=2.5 --param end_seconds=12.5 --param quality=85
```

## Procedure

1. Probe container and video/audio tracks (`artcraft_video_basic(action="probe")`).
2. Render a verification still frame at `preview_seconds` into `<work_dir>/preview_frame.png`.
3. Export the H.264 video into the staged destination and verify output non-emptiness.

## Pitfalls

- Ensure `end_seconds` is greater than `start_seconds` when trimming a custom span.
- Never export over the source footage path.

## Verification

- Inspect `<work_dir>/preview_frame.png` and confirm `source_sha256` and `output_sha256` in the run summary.
