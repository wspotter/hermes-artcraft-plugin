---
name: lightcraft-cli-edits
description: Inspect LightCraft CLI flags and verify exported images.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, lightcraft, photography, verification]
    related_skills: [artcraft-router, lightcraft-basics, photo-inspection]
---

# LightCraft CLI Edits Skill

Inspect installed `lightcraft-cli` capabilities with `lightcraft_run` and verify raster exports using `artcraft_inspect` and `artcraft_verify_edit`. For standard non-destructive photo development, prefer `lightcraft-basics` (`artcraft_develop`).

## When to Use

- Checking installed `lightcraft-cli` version or help output via `lightcraft_run`.
- Verifying raster exports created by LightCraft workflows when source and output share compatible dimensions.

## Prerequisites

- `lightcraft-cli` installed and discoverable via `artcraft_status`.

## How to Run

```json
{
  "name": "lightcraft_run",
  "arguments": {
    "cli_args": ["--help"]
  }
}
```

## Procedure

1. Call `lightcraft_run` with `cli_args: ["--help"]` or `cli_args: ["--version"]` to inspect available CLI options.
2. Use `artcraft_develop` (`hermes artcraft develop`) to render slider or preset adjustments to a new `output_path`.
3. Call `artcraft_inspect` on the exported image to verify decoded dimensions, format, color mode, and SHA-256 hash.
4. When source and output are same-dimension raster images, call `artcraft_verify_edit` to measure pixel-diff statistics.

## Pitfalls

- `lightcraft_run` only accepts `--help`, `-h`, `--version`, or `-V` for safe inspection; use `artcraft_develop` to execute actual image renders.

## Verification

- Confirm `artcraft_inspect` reports `exists: true`, non-zero width and height, and distinct `sha256` from the source file.
