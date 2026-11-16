---
name: soundcraft-basics
description: Inspect, convert, resample, and normalize audio files.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, soundcraft, audio, mastering, conversion]
    related_skills: [artcraft-router]
---

# SoundCraft Basics

Inspect audio metadata and convert, resample, normalize, or dither audio files without altering originals using `artcraft_audio_basic` (`soundcraft-cli info` and `soundcraft-cli convert`). Every conversion writes to a temp file first, checks that `source_sha256` is unchanged, and re-probes the output file.

## When to Use

- Checking sample rate, channel count, bit depth, frame count, duration, and Broadcast Wave (`bwf`) metadata (`action="info"`).
- Converting audio between formats (WAV, FLAC, AIFF, OGG, MP3) or changing `sample_rate` and `bit_depth` (`action="convert"`).
- Peak-normalizing (`normalize=true`) and controlling triangular dithering (`dither=true` or `dither=false`) during bit-depth reduction.

## Prerequisites

- `soundcraft-cli` installed and discoverable via `artcraft_status`.

## How to Run

### 1. Inspect Audio Metadata (`action="info"`)

```json
{
  "action": "info",
  "input_path": "<work_dir>/source/dialogue.wav"
}
```

CLI equivalent:
```bash
hermes artcraft audio info <work_dir>/source/dialogue.wav
```

### 2. Convert, Resample, and Normalize (`action="convert"`)

```json
{
  "action": "convert",
  "input_path": "<work_dir>/source/dialogue.wav",
  "output_path": "<work_dir>/exports/dialogue_48k_24b.wav",
  "sample_rate": 48000,
  "bit_depth": "24",
  "normalize": true,
  "dither": true
}
```

CLI equivalent:
```bash
hermes artcraft audio convert <work_dir>/source/dialogue.wav <work_dir>/exports/dialogue_48k_24b.wav \
  --rate 48000 \
  --bit-depth 24 \
  --normalize \
  --dither
```

## Procedure

1. Run `artcraft_audio_basic` with `action="info"` on `input_path` to record source `format`, `channels`, `sample_rate`, `sample_format`, `frames`, `seconds`, and `source_sha256`.
2. Run `artcraft_audio_basic` with `action="convert"`, passing a new `output_path` plus the desired `sample_rate`, `bit_depth` (`"16"`, `"24"`, or `"32f"`), `normalize`, and `dither` options.
3. Check the returned `output_info` block to confirm the exported file matches the requested sample rate, bit depth, and duration.

## Pitfalls

- Never overwrite `input_path`; `artcraft_audio_basic` rejects existing output paths unless `allow_overwrite=true` is explicitly set.
- Enable `dither=true` when reducing bit depth to `16` or `24` integer PCM to avoid quantization distortion; omit dithering when targeting `"32f"` floating-point output.

## Verification

- Every `action="convert"` call checks that `source_sha256` matches before and after conversion, confirms `output_path` is non-empty, and probes the output with `soundcraft-cli info` to populate `output_info`.
