---
name: recipe-voice-master
description: Clean and resample spoken-word audio to 48kHz WAV.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, recipe, soundcraft, audio, voice, wav]
    related_skills: [soundcraft-basics, filmcraft-basics, recipe-maker]
---

# Recipe: Voice Master

Probe spoken-word recordings and convert them cleanly to broadcast-ready `48kHz` `24-bit` normalized WAV via `soundcraft-cli`.

## When to Use

- Standardizing narration, voiceover, or podcast tracks prior to video assembly or publication.

## Prerequisites

- `soundcraft-cli` discoverable via `artcraft_status`.

## How to Run

```bash
hermes artcraft recipe run recipe-voice-master <work_dir>/source/voice.wav <work_dir>/exports/voice_48k.wav
```

Custom bit depth or sample rate:

```bash
hermes artcraft recipe run recipe-voice-master <work_dir>/source/voice.wav <work_dir>/exports/voice_16bit.wav \
  --param bit_depth=16 --param dither=true
```

## Procedure

1. Probe input sample rate, channel count, and frame count with `artcraft_audio_basic(action="info")`.
2. Convert and normalize into a distinct destination file via `artcraft_audio_basic(action="convert")`.

## Pitfalls

- Only enable `dither=true` when targeting `16-bit` PCM outputs or leave enabled on `24-bit` safely when desired; keep `bit_depth` in `["16", "24", "32f"]`.
- Never write over the original recording path.

## Verification

- Confirm `output_info.sample_rate` matches target `48000` Hz and `source_sha256` is unchanged.
