---
name: filmcraft-basics
description: Probe media, extract still frames, and export video clips.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, filmcraft, video, frame-extraction, transcoding]
    related_skills: [artcraft-router, photo-inspection]
---

# FilmCraft Basics Skill

Probe video and audio containers, render still PNG frames, and trim or transcode standalone video clips and `.fcproj` projects non-destructively using `artcraft_video_basic` (`filmcraft-cli`). Every operation preserves the original input file and verifies the exported artifact.

## When to Use

- Inspecting video container streams, codecs, frame rate, resolution, and duration (`action="probe"`).
- Extracting a lossless PNG still frame at an exact timestamp (`action="render_frame"`) from a video clip or `.fcproj` timeline.
- Trimming (`start_seconds`, `end_seconds`), scaling (`scale`), or transcoding (`format`, `preset`, `quality`, `no_audio`) a standalone video clip or `.fcproj` project (`action="export"`).

## Prerequisites

- `filmcraft-cli` installed and discoverable via `artcraft_status`.

## How to Run

### 1. Probe Container Metadata (`action="probe"`)

```json
{
  "action": "probe",
  "input_path": "<work_dir>/source/clip.mp4"
}
```

CLI equivalent:
```bash
hermes artcraft video probe <work_dir>/source/clip.mp4
```

### 2. Render a Still PNG Frame (`action="render_frame"`)

```json
{
  "action": "render_frame",
  "input_path": "<work_dir>/source/clip.mp4",
  "output_path": "<work_dir>/previews/frame_02s.png",
  "seconds": 2.5,
  "scale": 1.0
}
```

CLI equivalent:
```bash
hermes artcraft video render-frame <work_dir>/source/clip.mp4 <work_dir>/previews/frame_02s.png \
  --seconds 2.5 \
  --scale 1.0
```

### 3. Trim and Export Video (`action="export"`)

```json
{
  "action": "export",
  "input_path": "<work_dir>/source/clip.mp4",
  "output_path": "<work_dir>/exports/clip_trimmed.mp4",
  "start_seconds": 1.0,
  "end_seconds": 6.0,
  "format": "mp4",
  "preset": "web_high",
  "scale": 1.0
}
```

CLI equivalent:
```bash
hermes artcraft video export <work_dir>/source/clip.mp4 <work_dir>/exports/clip_trimmed.mp4 \
  --start 1.0 \
  --end 6.0 \
  --format mp4 \
  --preset web_high \
  --scale 1.0
```

## Procedure

1. Call `artcraft_video_basic` with `action="probe"` to inspect duration, resolution, frame rate, and `source_sha256`.
2. To inspect visual quality at a timestamp, call `artcraft_video_basic` with `action="render_frame"` and a `.png` `output_path`, then inspect the frame with `artcraft_inspect`.
3. To export or trim a clip or `.fcproj` project, call `artcraft_video_basic` with `action="export"`, providing `start_seconds`, `end_seconds`, `format`, `preset`, and `scale`.

## Pitfalls

- `render_frame` requires an output path ending in `.png` and decodes the resulting PNG to verify dimensions.
- When trimming with `start_seconds` and `end_seconds`, confirm both timestamps lie within the probed clip duration (`end_seconds > start_seconds >= 0`).
- Never overwrite `input_path`; always write to a new path under `<work_dir>/previews/` or `<work_dir>/exports/`.

## Verification

- `render_frame` verifies that `source_sha256` is unchanged and decodes the output PNG to confirm non-zero `width` and `height`.
- `export` verifies that `source_sha256` is unchanged, `output_path` exists with non-zero `size_bytes`, and records `output_sha256`.
