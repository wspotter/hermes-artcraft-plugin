---
name: recipe-film-matte
description: Apply warm matte film contrast via LightCraft CLI.
version: "0.1.0"
author: "wspotter"
license: "MIT"
platforms: [linux, macos]
metadata:
  hermes:
    category: creative
    tags: [artcraft, recipe, lightcraft, photography, grading]
    related_skills: [lightcraft-basics, photo-inspection, recipe-maker]
---

# Recipe: Film Matte

Develop a photo with lifted matte shadows, gentle highlight roll-off, and subtle warm film contrast using `lightcraft-cli` while keeping the source file unchanged.

## When to Use

- Toning portraits, editorial stills, or product shots for a soft matte film print feel.

## Prerequisites

- `lightcraft-cli` discoverable via `artcraft_status`.

## How to Run

```bash
hermes artcraft recipe run recipe-film-matte <work_dir>/source/photo.png <work_dir>/exports/photo_matte.jpg
```

Override defaults cleanly:

```bash
hermes artcraft recipe run recipe-film-matte <work_dir>/source/photo.png <work_dir>/exports/photo_matte.jpg \
  --param contrast=15 --param shadows=20 --param long_edge=2048
```

## Procedure

1. Inspect source framing and tone metrics (`artcraft_inspect`).
2. Develop non-destructively via `artcraft_develop` with matte tone curves and optional long-edge scaling.
3. Verify the rendered export and dimensions against source via `artcraft_build_review`.

## Pitfalls

- Keep `blacks` modest (`+8..+18`) so deep shadow detail remains milky rather than muddy.
- Never target `input_path` as the destination file.

## Verification

- Confirm `source_sha256` matches the pre-run hash, `output_path` decodes cleanly, and `review` checks pass.
