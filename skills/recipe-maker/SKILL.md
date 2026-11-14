---
name: recipe-maker
description: Design, test, and save reusable ArtCraft workflow skills.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, recipes, workflow, authoring, automation]
    related_skills:
      - artcraft-router
      - photo-inspection
      - photo-restoration
      - lightcraft-basics
      - soundcraft-basics
      - filmcraft-basics
---

# Recipe Maker Skill

Design, prototype, verify, and save a new reusable ArtCraft recipe skill across `PhotoCraft`, `LightCraft`, `FilmCraft`, and `SoundCraft` using bundled `artcraft:recipe-*` skills as reference templates.

## When to Use

- Turning a multi-step photo development, restoration, print formatting, audio mastering, or video export sequence into a repeatable `recipe-<slug>` skill.
- Capturing tuned slider ranges, safe parameter bounds, and Stop/Ask quality gates after an interactive editing session.

## Prerequisites

- ArtCraft CLI suite discoverable via `artcraft_status`.
- At least one representative sample media file to test candidate steps non-destructively.

## How to Run

### 1. Initialize a Prototype Job Workspace

```bash
hermes artcraft job create --job-root <work_dir>/recipe_proto --source <work_dir>/sample.png
```

Or invoke `artcraft_job` with `action="init"`, `job_dir="<work_dir>/recipe_proto"`, and `source_path="<work_dir>/sample.png"`.

### 2. Validate the New Recipe Against Hermes Standards

```bash
python3 -m unittest tests/test_skill_standards.py -v
```

## Procedure

1. **Probe & Inspect**:
   - Call `artcraft_status` (and `photocraft_run` or `lightcraft_run` when checking CLI flags) to confirm binary capabilities.
   - Inspect the sample input first: call `artcraft_prepare_inspection` for photographs, `artcraft_audio_basic` with `action="info"` for audio, or `artcraft_video_basic` with `action="probe"` for video. Record the baseline metrics that trigger the recipe.
2. **Prototype Non-Destructively**:
   - Initialize a workspace with `artcraft_job(action="init")`.
   - Test candidate steps (`artcraft_develop`, `artcraft_restore_step`, `photocraft_spot_heal`, `artcraft_prepare_print`, `artcraft_audio_basic`, `artcraft_video_basic`) writing each stage to a distinct disposable path in `<work_dir>/work/` while preserving `source_sha256`.
   - Determine conservative default parameters and explicit safe bounds.
3. **Verify Before/After Quality**:
   - Run `artcraft_build_review` or `artcraft_verify_edit` (or audio/video stream checks) on the prototype output.
   - Define concrete acceptance checks and explicit Stop/Ask thresholds (`status: "needs_decision"` or `status: "needs_clarification"`) where human review is required.
4. **Author & Save the Recipe Skill**:
   - Because bundled plugin skills (`artcraft:recipe-*`) are read-only at runtime, save newly created user recipes into the user's writable skills directory (`~/.hermes/skills/recipe-<slug>/SKILL.md` or `<workspace_dir>/skills/recipe-<slug>/SKILL.md`, or via `skill_manage`). Only write to `skills/recipe-<slug>/SKILL.md` inside the plugin repository when explicitly developing upstream plugin skills.
   - Use the bundled `artcraft:recipe-*` skills as reference templates and follow this exact YAML frontmatter and six-section structure:

```markdown
---
name: recipe-<slug>
description: Short summary under sixty chars ending with a period.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, recipe, <domain-tag>]
    related_skills: [artcraft-router]
---

# Recipe: <Title> Skill

Brief overview of the workflow, tools invoked, and non-destructive guarantees.

## When to Use

- Baseline inspection metrics or user goals that trigger this recipe.

## Prerequisites

- Required ArtCraft binaries and baseline inspection steps.

## How to Run

Tool payload or paste-safe CLI invocation using `<work_dir>` placeholders.

## Procedure

1. Step-by-step parameter ranges and safe defaults.

## Pitfalls

- Conditions that require stopping with `needs_decision` or `needs_clarification`.

## Verification

- Post-edit visual crop checks, SHA-256 receipts, or stream validation rules.
```

5. **Validate Standards**:
   - Register `recipe-<slug>` in `skills/artcraft-router/SKILL.md`, `README.md`, and `EXPECTED_SKILLS` in `tests/test_skill_standards.py`.
   - Run `python3 -m unittest tests/test_skill_standards.py -v` and confirm all checks pass.

## Pitfalls

- Never hardcode machine-local paths, private hostnames, or temporary system paths in a recipe skill; always use `<work_dir>` placeholders.
- Keep `description` single-line, at most 60 characters, ending with a period, without repeating the skill name or marketing buzzwords.
- Never place inline comments immediately after a backslash line continuation in shell code fences.

## Verification

- `python3 -m unittest tests/test_skill_standards.py -v` passes with zero errors.
- Prototype run produces verified `source_sha256` and `output_sha256` receipts and clean review crops.
