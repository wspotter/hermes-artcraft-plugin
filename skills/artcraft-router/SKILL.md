---
name: artcraft-router
description: Route image and photo editing tasks to the right ArtCraft CLI tool and enforce post-edit verification.
---

# ArtCraft Router

Use ArtCraft's CLI tools instead of GUI clicking whenever possible:

1. **Check availability first** with `artcraft_status` if you haven't verified which binaries are installed in this session.
2. **Inspect the photograph first**: Load the `photo-inspection` skill. Use `artcraft_prepare_inspection` to generate whole-photo previews, 1:1 native crops, print PPI ratings, and measured clues (endpoint clipping, sharpness, noise) without altering the source file. For quick metadata checks, use `artcraft_inspect`.
3. For a localized blemish or scratch, load `photocraft-cli-edits` and use `photocraft_spot_heal`. Review the changed area before delivery.
4. For LightCraft discovery, load `lightcraft-cli-edits`. Use `artcraft_verify_edit` to compare compatible raster exports made through your configured workflow.
5. **Prepare print files**: Load the `print-preparation` skill. Use `artcraft_prepare_print` to calculate dimensions and target PPI, enforce the aspect ratio clarification gate (borderless crop vs margins), preserve color profiles and master copies, and verify the final deliverable.
6. **Apply restoration recipes**: Load the `photo-restoration` skill (or modular recipe skills `recipe-faded-tones`, `recipe-color-cast`, `recipe-dust-scratches`, `recipe-noise-grain`, `recipe-sharpening`, `recipe-enlargement`). Use `artcraft_restore_step` to execute incremental edits with checkpointing and matching native 1:1 and print-scale before/after crops. Enforce the Stop/Ask Gate (`status: "needs_decision"`) before reconstructing missing faces, lettering, or important missing content. Use `artcraft_checkpoint` to inspect or audit restoration history.
7. **Build structured review packages**: Use `artcraft_build_review` to generate whole-photo previews, 1:1 native crops, source/output SHA-256 hashes, mechanical checks, and quality-trap flags (untouched scratch / no-op, unauthorized framing or aspect shift, and smeared repairs with variance collapse >80%) with bounded retry tracking.
8. **Manage job workspaces & delivery receipts**: Use `artcraft_job` to create deterministic job folders (`source/`, `work/`, `previews/`, `exports/`, `job.json`), checkpoint work stages, resume from the last verified checkpoint after interruptions, record verified export artifacts, and reconcile uncertain delivery receipts before retrying to prevent duplicate delivery.
