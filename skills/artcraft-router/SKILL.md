---
name: artcraft-router
description: Route image and photo editing tasks to the right ArtCraft CLI tool and enforce post-edit verification.
---

# ArtCraft Router

Use ArtCraft's CLI tools instead of GUI clicking whenever possible:

1. **Check availability first** with `artcraft_status` if you haven't verified which binaries are installed in this session.
2. **Inspect the input** with `artcraft_inspect` to get exact dimensions, color mode, and SHA-256 before planning coordinates or crops.
3. **Pick the right app:**
   - **PhotoCraft (`photocraft_run`)**: Layer edits, spot-healing, retouching, borders/mattes, resizing, and print/proof exports. Load `photocraft-cli-edits`.
   - **LightCraft (`lightcraft_run`)**: RAW development, exposure/white-balance/color presets, catalog queries, and batch photo export. Load `lightcraft-cli-edits`.
4. **Never overwrite originals.** Always write to a new output path and verify pixel changes with `artcraft_verify_edit` (automatic when `input_path` and `output_path` are passed to `photocraft_run` / `lightcraft_run`).
