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

# Recipe Maker

Design, test, and save a reusable ArtCraft workflow skill across PhotoCraft, LightCraft, FilmCraft, and SoundCraft using the bundled `recipe-*` skills as templates.

## When to Use

- Turning a multi-step photo edit, restoration, print layout, audio conversion, or video export sequence into a repeatable `recipe-<slug>` skill.
- Capturing tuned slider ranges, safe parameter bounds, and pause conditions after an interactive editing session.

## Prerequisites

- ArtCraft CLI binaries discoverable via `artcraft_status`.
- At least one representative sample media file to test each step non-destructively.

## How to Run

### 1. Initialize a Prototype Job Workspace

```bash
hermes artcraft job init recipe_proto --workspace <work_dir> --source <work_dir>/sample.png
```

Or invoke `artcraft_job` with `action="init"`, `job_id="recipe_proto"`, `workspace_dir="<work_dir>"`, and `source_path="<work_dir>/sample.png"`.

### 2. Validate Bundled Repo Skills (Plugin Contributors Only)

```bash
python3 -m unittest tests/test_skill_standards.py -v
```

## Procedure

1. Probe and inspect the sample input first. Call `artcraft_status` (plus `photocraft_run` or `lightcraft_run` with `["--help"]` when checking CLI flags), then inspect the input with `artcraft_prepare_inspection` (images), `artcraft_audio_basic` `action="info"` (audio), or `artcraft_video_basic` `action="probe"` (video). Record the baseline numbers that trigger the recipe.
2. Prototype non-destructively in a job workspace (`artcraft_job` `action="init"`). Run candidate steps (`artcraft_develop`, `artcraft_restore_step`, `photocraft_spot_heal`, `artcraft_prepare_print`, `artcraft_audio_basic`, `artcraft_video_basic`) writing each stage to a new file under `<work_dir>/work/` while keeping `source_sha256` intact. Pick conservative defaults and clear safety bounds.
3. Verify before/after quality with `artcraft_build_review` or `artcraft_verify_edit` (or audio/video stream checks), and write down when the recipe must stop and ask for confirmation (`status: "needs_decision"` or `status: "needs_clarification"`).
4. Save the recipe skill to the right place:
   - For your own personal recipes (bundled plugin skills are read-only at runtime), save to `~/.hermes/skills/recipe-<slug>/SKILL.md` (or `<workspace_dir>/skills/recipe-<slug>/SKILL.md`, or via `skill_manage`).
   - Only write to `skills/recipe-<slug>/SKILL.md` inside this plugin repository when contributing a new bundled skill upstream.

Use this frontmatter and six-section layout:

```markdown
---
name: recipe-<slug>
description: Short summary under sixty chars ending with a period.
version: "0.1.0"
author: "<your-handle>"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, recipe, <domain-tag>]
    related_skills: [artcraft-router]
---

# Recipe: <Title>

Brief overview of what the workflow does, which tools it calls, and how it protects originals.

## When to Use

- Baseline inspection metrics or user goals that trigger this recipe.

## Prerequisites

- Required ArtCraft binaries and baseline inspection steps.

## How to Run

Tool payload or paste-safe CLI invocation using `<work_dir>` placeholders.

## Procedure

1. Step-by-step parameter ranges and safe defaults.

## Pitfalls

- Conditions that require pausing with `needs_decision` or `needs_clarification`.

## Verification

- Post-edit visual crop checks, SHA-256 verification, or stream validation rules.
```

5. If contributing a bundled skill to this repository, set `author` to match the repo maintainer standards, register `recipe-<slug>` in `skills/artcraft-router/SKILL.md`, `README.md`, and `EXPECTED_SKILLS` in `tests/test_skill_standards.py`, and run `python3 -m unittest tests/test_skill_standards.py -v`.

## Pitfalls

- Never hardcode machine-local paths, private hostnames, or system temp directory paths in a recipe skill; always use `<work_dir>` placeholders.
- Keep `description` single-line, at most 60 characters, ending with a period, without repeating the skill name or marketing buzzwords.
- Never place inline `#` comments immediately after a backslash line continuation in shell fences, and avoid raw shell text/file commands in skill instructions.

## Verification

- Personal recipes run cleanly on a fresh sample file, preserve `source_sha256`, and pass visual crop or stream checks.
- Upstream repo contributions also pass `python3 -m unittest tests/test_skill_standards.py -v`.
