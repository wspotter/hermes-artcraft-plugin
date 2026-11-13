---
name: lightcraft-cli-edits
description: Recipe for non-destructive LightCraft CLI RAW development, presets, and verified exports.
---

# LightCraft CLI Edits

1. Check `lightcraft-cli` capabilities if needed (`lightcraft_run` with `cli_args: ["--help"]`, `verify: false`).
2. Inspect source dimensions/format with `artcraft_inspect` when working with raster inputs.
3. Run development or export commands via `lightcraft_run` with a distinct `output_path`.
4. When `input_path` and `output_path` are both raster images, keep `verify: true` (default) and pass `expected_width` / `expected_height` whenever targeting a specific output size.
