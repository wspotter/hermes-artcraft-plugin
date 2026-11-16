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

# FilmCraft Basics

Probe video and audio containers, extract still PNG frames, and trim or transcode standalone video clips and `.fcproj` projects without modifying source files using `artcraft_video_basic` (`filmcraft-cli`).

## When to Use

- Inspecting video container streams, codecs, frame rate, resolution, and duration (`action="probe"`).
- Extracting a still PNG frame at a timestamp (`action="render_frame"`) from a video clip or `.fcproj` timeline.
- Trimming (`start_seconds`, `end_seconds`), scaling (`scale`), or transcoding (`format`, `preset`, `quality`, `no_audio`) a video clip or `.fcproj` project (`action="export"`).

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
hermes artcraft video probe --input <work_dir>/source/clip.mp4
```

### 2. Render a Still PNG Frame (`action="render_frame"`)

```json
{
  "action": "render_frame",
  "input_path": "<work_dir>/source/clip.mp4",
  "output_path": "<work_dir>/previews/frame_2_5s.png",
  "seconds": 2.5,
  "scale": 1.0
}
```

CLI equivalent:
```bash
hermes artcraft video render_frame --input <work_dir>/source/clip.mp4 \
  -o <work_dir>/previews/frame_2_5s.png \
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
hermes artcraft video export --input <work_dir>/source/clip.mp4 \
  -o <work_dir>/exports/clip_trimmed.mp4 \
  --start 1.0 \
  --end 6.0 \
  --format mp4 \
  --preset web_high \
  --scale 1.0
```

## Procedure

1. Call `artcraft_video_basic` with `action="probe"` to inspect duration, resolution, frame rate, and `source_sha256`.
2. To review visual quality at a timestamp, call `artcraft_video_basic` with `action="render_frame"` and a `.png` `output_path`, then check the image with `artcraft_inspect`.
3. To export or trim a clip or `.fcproj` project, call `artcraft_video_basic` with `action="export"` and the desired `start_seconds`, `end_seconds`, `format`, `preset`, and `scale`.

## Pitfalls

- `render_frame` writes PNG image bytes, so keep the `output_path` extension `.png` to match the file format.
- When trimming with `start_seconds` and `end_seconds`, confirm both timestamps fit inside the probed clip duration (`end_seconds > start_seconds >= 0`).
- Never overwrite `input_path`; write outputs to a fresh path under `<work_dir>/previews/` or `<work_dir>/exports/`.

## Verification

- `render_frame` verifies that `source_sha256` is unchanged and decodes the output PNG to confirm non-zero `width` and `height`.
- `export` verifies that `source_sha256` is unchanged, confirms `output_path` is non-empty, and reports `size_bytes` and `output_sha256`.
