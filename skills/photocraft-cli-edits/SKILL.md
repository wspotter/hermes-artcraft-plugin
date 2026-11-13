---
name: photocraft-cli-edits
description: Recipe for running non-destructive PhotoCraft CLI edits with automatic pixel-diff verification.
---

# PhotoCraft CLI Edits

1. Inspect the source image with `artcraft_inspect` to confirm `width`, `height`, and `mode`.
2. Discover supported subcommands/flags on the host binary if needed (`photocraft_run` with `cli_args: ["--help"]`, `verify: false`).
3. Run the edit with `photocraft_run`, always passing:
   - `cli_args`: exact PhotoCraft CLI arguments
   - `input_path`: original image path
   - `output_path`: a distinct output path (never the same file as `input_path`)
   - `region`: `[x, y, width, height]` when editing a localized defect so verification confirms pixels changed inside that region
4. If verification returns `no_op_edit` or `no_op_in_region`, **do not report success** — inspect the CLI output/flags and re-run with corrected coordinates or parameters.
