---
name: artcraft-router
description: Route image and photo editing tasks to the right ArtCraft CLI tool and enforce post-edit verification.
---

# ArtCraft Router

Use ArtCraft's CLI tools instead of GUI clicking whenever possible:

1. **Check availability first** with `artcraft_status` if you haven't verified which binaries are installed in this session.
2. **Inspect the input** with `artcraft_inspect` to get exact dimensions, color mode, and SHA-256 before planning coordinates or crops.
3. For a localized blemish, load `photocraft-cli-edits` and use `photocraft_spot_heal`. Review the changed area before delivery.
4. For LightCraft discovery, load `lightcraft-cli-edits`. Use `artcraft_verify_edit` to compare compatible raster exports made through your configured workflow.
