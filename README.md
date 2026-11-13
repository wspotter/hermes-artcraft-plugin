# hermes-artcraft-plugin

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin for driving the **ArtCraft** creative suite (**PhotoCraft**, **LightCraft**, **FilmCraft**, **SoundCraft**) via their paired CLI tools—with non-destructive output guards and automatic post-edit pixel-diff verification.

## What it does

PhotoCraft spot healing stages a copy of the source, executes a typed stroke,
and publishes a fresh PNG only after confirming changes inside the allowed
region and zero changes outside it. The receipt records source and output
hashes. Inspect the repaired area visually before delivery.

The plugin discovers all four CLIs. PhotoCraft and LightCraft also expose
help and version probes. Automated editing covers PhotoCraft spot healing,
print preparation with clarification gates, and 6 modular photo restoration recipes
with incremental checkpointing, before/after crops, and an automated Stop/Ask gate.

## Installation

### Option 1: Clone into Hermes plugins directory
```bash
git clone https://github.com/wspotter/hermes-artcraft-plugin.git ~/.hermes/plugins/artcraft
```

### Option 2: Editable pip install (for development)
```bash
git clone https://github.com/wspotter/hermes-artcraft-plugin.git
cd hermes-artcraft-plugin
pip install -e ".[dev]"
```

Enable the `artcraft` plugin in Hermes (`config.yaml` under `plugins.enabled: [artcraft]`) and make Pillow available in its Python environment.

The plugin discovers ArtCraft binaries on `PATH`, in `ARTCRAFT_BIN_DIR`, in the active Hermes profile (`$HERMES_HOME/bin` or `~/.hermes/profiles/<profile>/bin`), and in standard ArtCraft locations (`~/.local/bin`, `~/bin`, `/usr/local/bin`). Set `ARTCRAFT_BIN_DIR` to explicitly override CLI paths.

## Tools Registered (`toolset: artcraft`)

| Tool | Purpose |
|---|---|
| `artcraft_status` | Discover installed ArtCraft CLIs and report paths + versions |
| `artcraft_inspect` | Quick check: format, color mode, dimensions, DPI, orientation, and SHA-256 |
| `artcraft_prepare_inspection` | Generate whole-photo preview, 1:1 native crops, print PPI, and measured clues |
| `artcraft_prepare_print` | Prepare verified print file at target dimensions/PPI with clarification gate |
| `artcraft_restore_step` | Execute verified restoration recipes with checkpointing, dual crops, and Stop/Ask gate |
| `artcraft_checkpoint` | List or inspect restoration checkpoints, manifests, and crop comparisons |
| `artcraft_verify_edit` | Verify output validity, dimensions, and pixel diff (full image or `[x, y, w, h]` region) |
| `photocraft_spot_heal` | Apply a localized stroke and publish a verified PNG |
| `photocraft_run` | Show PhotoCraft CLI help or version |
| `lightcraft_run` | Show LightCraft CLI help or version |

## CLI Subcommands

```bash
hermes artcraft doctor
hermes artcraft inspect <path> [--working-dir DIR] [--preview-max DIM] [--crop-size SIZE]
hermes artcraft prep-print <input_path> <output_path> --width W --height H [--ppi PPI] [--fit-mode MODE] [--confirm-crop]
hermes artcraft restore <recipe> <input_path> <output_path> [--params JSON] [--region X Y W H] [--checkpoint-dir DIR]
hermes artcraft checkpoint {list,get} <checkpoint_dir> [--step-id ID]
hermes artcraft verify <input_path> <output_path> [--width W] [--height H] [--region X Y W H]
```

Or standalone without Hermes:
```bash
python -m artcraft_plugin.cli doctor
python -m artcraft_plugin.cli inspect input.png --preview-max 1024 --crop-size 256
python -m artcraft_plugin.cli prep-print input.png output.png --width 8 --height 10 --fit-mode margins
python -m artcraft_plugin.cli restore faded_tones input.png output.png --params '{"in_black": 15, "in_white": 240}'
python -m artcraft_plugin.cli checkpoint list ./checkpoints
python -m artcraft_plugin.cli verify input.png output.png --region 100 100 64 64
```

## Skills Included

Generic, on-demand `SKILL.md` recipes live in [`skills/`](skills/):
- `artcraft-router` — choose the right app/tool and enforce inspect → edit → verify
- `photo-inspection` — whole-photo preview and 1:1 native crops visual inspection recipe
- `photo-restoration` — non-destructive restoration recipes, checkpointing, and Stop/Ask gate
- `print-preparation` — print sizing, aspect-ratio clarification gate, margins/crop, and delivery verification
- `recipe-faded-tones` — gentle levels and dynamic range restoration preserving highlight/shadow detail
- `recipe-color-cast` — neutral-balance color correction preserving skin tones and warmth
- `recipe-dust-scratches` — localized healing preserving nearby edges and authentic texture
- `recipe-noise-grain` — selective noise reduction retaining facial detail, lettering, and texture
- `recipe-sharpening` — restrained unsharp mask avoiding halos and noise amplification
- `recipe-enlargement` — proportional upscaling and output sharpening preserving composition
- `photocraft-cli-edits` — non-destructive PhotoCraft CLI workflow with region verification
- `lightcraft-cli-edits` — non-destructive LightCraft CLI development & export workflow

## Development

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT
