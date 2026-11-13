# hermes-artcraft-plugin

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin for driving the **ArtCraft** creative suite (**PhotoCraft**, **LightCraft**, **FilmCraft**, **SoundCraft**) via their paired CLI tools—with non-destructive output guards and automatic post-edit pixel-diff verification.

## What it does

PhotoCraft spot healing stages a copy of the source, executes a typed stroke,
and publishes a fresh PNG only after confirming changes inside the allowed
region and zero changes outside it. The receipt records source and output
hashes. Inspect the repaired area visually before delivery.

The plugin discovers all four CLIs. PhotoCraft and LightCraft also expose
help and version probes. Automated editing currently covers PhotoCraft spot healing.

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
| `artcraft_inspect` | Inspect image format, color mode, dimensions, DPI, and SHA-256 |
| `artcraft_verify_edit` | Verify output validity, dimensions, and pixel diff (full image or `[x, y, w, h]` region) |
| `photocraft_spot_heal` | Apply a localized stroke and publish a verified PNG |
| `photocraft_run` | Show PhotoCraft CLI help or version |
| `lightcraft_run` | Show LightCraft CLI help or version |

## CLI Subcommands

```bash
hermes artcraft doctor
hermes artcraft verify <input_path> <output_path> [--width W] [--height H] [--region X Y W H]
```

Or standalone without Hermes:
```bash
python -m artcraft_plugin.cli doctor
python -m artcraft_plugin.cli verify input.png output.png --region 100 100 64 64
```

## Skills Included

Generic, on-demand `SKILL.md` recipes live in [`skills/`](skills/):
- `artcraft-router` — choose the right app/tool and enforce inspect → edit → verify
- `photocraft-cli-edits` — non-destructive PhotoCraft CLI workflow with region verification
- `lightcraft-cli-edits` — non-destructive LightCraft CLI development & export workflow

## Development

```bash
ruff check .
pytest -v
```

## License

MIT
