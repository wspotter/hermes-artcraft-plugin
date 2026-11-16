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

# LightCraft CLI Edits

Inspect installed `lightcraft-cli` options with `lightcraft_run` and check raster exports using `artcraft_inspect` and `artcraft_verify_edit`. For photo development and rendering, use `lightcraft-basics` (`artcraft_develop`).

## When to Use

- Checking installed `lightcraft-cli` version or help output via `lightcraft_run`.
- Verifying raster exports from LightCraft workflows when source and output share the same dimensions.

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

1. Call `lightcraft_run` with `cli_args: ["--help"]` or `cli_args: ["--version"]` to check available CLI options.
2. Use `artcraft_develop` (`hermes artcraft develop`) to render slider or preset adjustments to a new `output_path`.
3. Call `artcraft_inspect` on the exported image to check decoded dimensions, format, color mode, and `sha256`.
4. When source and output are same-dimension raster images, call `artcraft_verify_edit` to measure pixel-diff statistics.

## Pitfalls

- `lightcraft_run` only accepts `["--help"]` or `["--version"]` (short flags like `-h` or `-V` are rejected); use `artcraft_develop` to run actual image renders.

## Verification

- Confirm `artcraft_inspect` reports `ok: true`, `valid: true`, non-zero `width` and `height`, and a different `sha256` from the source file.
