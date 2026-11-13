# hermes-artcraft-plugin

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin for driving the **ArtCraft** creative suite (**PhotoCraft**, **LightCraft**, **FilmCraft**, **SoundCraft**) via their paired CLI tools—with non-destructive output guards and automatic post-edit pixel-diff verification.

## Why This Plugin Exists

ArtCraft apps expose headless CLIs and MCP servers, but agents still hit two common failure modes:
1. **Silent no-op edits:** A command exits `0` while writing an untouched copy of the input image.
2. **Accidental overwrites or GUI fragility:** Driving the GUI is slow and easily blocked by dialogs, while raw shell commands can clobber source files.

`hermes-artcraft-plugin` wraps ArtCraft CLI execution in typed tools that:
- Auto-discover paired `*-cli` binaries (`photocraft-cli`, `lightcraft-cli`, `filmcraft-cli`, `soundcraft-cli`).
- Refuse to overwrite `input_path` with `output_path`.
- Automatically verify that the output image is valid, matches optional target dimensions, and has **non-zero pixel changes** (globally or within a target `[x, y, w, h]` region).

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

Set `ARTCRAFT_BIN_DIR` if your ArtCraft `*-cli` binaries live outside `PATH` and `~/.local/bin`.

## Tools Registered (`toolset: artcraft`)

| Tool | Purpose |
|---|---|
| `artcraft_status` | Discover installed ArtCraft CLIs and report paths + versions |
| `artcraft_inspect` | Inspect image format, color mode, dimensions, DPI, and SHA-256 |
| `artcraft_verify_edit` | Verify output validity, dimensions, and pixel diff (full image or `[x, y, w, h]` region) |
| `photocraft_run` | Run `photocraft-cli` with non-destructive guard + automatic `verify_edit` |
| `lightcraft_run` | Run `lightcraft-cli` with non-destructive guard + automatic `verify_edit` |

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
