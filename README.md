# hermes-artcraft-plugin

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin and unified stdio MCP server for driving the **ArtCraft** creative suite (**PhotoCraft**, **LightCraft**, **FilmCraft**, **SoundCraft**) via their paired CLI binaries—with non-destructive output guards, SHA-256 source integrity checks, and automatic post-edit verification.

## What It Does

- **Unified 4-App Coverage**: Discovers and wraps `photocraft-cli`, `lightcraft-cli`, `filmcraft-cli`, and `soundcraft-cli` behind one Hermes plugin (`register(ctx)`) and one stdio MCP server (`python3 -m artcraft_plugin.mcp_server`).
- **Non-Destructive by Construction**: Every editing or export tool writes to a new output path, verifies that `source_sha256` is unchanged before and after execution, and decodes or probes the output artifact before returning a receipt.
- **PhotoCraft**: Localized spot healing with region-bounded pixel-diff verification (`outside_region_changed_pixels == 0`), print preparation with aspect-ratio clarification gates, and 6 checkpointed restoration recipes with dual-scale 1:1 native + print-scale crops and a Stop/Ask gate (`status: "needs_decision"`).
- **LightCraft**: Non-destructive photo development and rendering (`artcraft_develop`) supporting exposure/color/detail sliders (`--set KEY=VALUE`), presets, long-edge resizing, and export quality verification.
- **SoundCraft**: Audio stream inspection (`info`) and non-destructive format conversion, resampling, bit-depth selection (`16`, `24`, `32f`), peak normalization, and dithering (`artcraft_audio_basic`).
- **FilmCraft**: Media container probing (`probe`), lossless PNG frame extraction (`render_frame`), and non-destructive clip or `.fcproj` timeline trimming and export (`artcraft_video_basic`).
- **Review & Job Workspaces**: Structured before/after review packages with quality-trap detection (`artcraft_build_review`) and deterministic job workspaces with checkpointing and delivery receipt reconciliation (`artcraft_job`).

## Installation

### Option 1: Install from the Hermes Plugin Catalog
```bash
hermes plugins install artcraft
```

### Option 2: Clone into Hermes plugins directory
```bash
git clone https://github.com/wspotter/hermes-artcraft-plugin.git ~/.hermes/plugins/artcraft
```

### Option 3: Editable pip install (for development)
```bash
git clone https://github.com/wspotter/hermes-artcraft-plugin.git
cd hermes-artcraft-plugin
pip install -e ".[dev]"
```

Enable the `artcraft` plugin in Hermes (`config.yaml` under `plugins.enabled: [artcraft]`) and ensure Pillow (`PIL`) is available in its Python environment.

The plugin discovers ArtCraft binaries on `PATH`, in `ARTCRAFT_BIN_DIR`, in the active Hermes profile (`$HERMES_HOME/bin` or `~/.hermes/profiles/<profile>/bin`), and in standard locations (`~/.local/bin`, `~/bin`, `/usr/local/bin`). Set `ARTCRAFT_BIN_DIR` to explicitly override CLI paths.

## Unified Stdio MCP Server

Any MCP-compatible agent client can launch the unified stdio MCP server directly:

```bash
python3 -m artcraft_plugin.mcp_server
```

## Tools Registered

The plugin registers **15 Hermes tools** (`toolset: artcraft`) and exposes **13 high-level tools over the stdio MCP server**:

| Tool | Hermes Plugin | MCP Server | App / Scope | Purpose |
|---|:---:|:---:|---|---|
| `artcraft_status` | Yes | Yes | All 4 Apps | Discover installed ArtCraft CLIs and report paths + versions |
| `artcraft_inspect` | Yes | Yes | Photo / Raster | Quick check: format, color mode, dimensions, DPI, orientation, and SHA-256 |
| `artcraft_prepare_inspection` | Yes | Yes | Photo / Raster | Generate whole-photo preview, 1:1 native crops, print PPI, and measured clues |
| `photocraft_spot_heal` | Yes | Yes | PhotoCraft | Apply a localized healing stroke and verify zero changes outside `region` |
| `artcraft_develop` | Yes | Yes | LightCraft | Develop and render photos non-destructively with sliders, presets, and sizing |
| `artcraft_audio_basic` | Yes | Yes | SoundCraft | Inspect audio metadata (`info`) or convert, resample, normalize, and dither (`convert`) |
| `artcraft_video_basic` | Yes | Yes | FilmCraft | Probe video containers (`probe`), extract PNG frames (`render_frame`), or trim/export (`export`) |
| `artcraft_prepare_print` | Yes | Yes | PhotoCraft / PIL | Prepare verified print files at target dimensions/PPI with aspect-ratio clarification gate |
| `artcraft_restore_step` | Yes | Yes | PhotoCraft | Execute verified restoration recipes with checkpointing, dual crops, and Stop/Ask gate |
| `artcraft_checkpoint` | Yes | Yes | PhotoCraft | List or inspect restoration checkpoints, manifests, and crop comparisons |
| `artcraft_build_review` | Yes | Yes | Review / QA | Build before/after review packages with mechanical checks and quality-trap flags |
| `artcraft_job` | Yes | Yes | Workflow | Manage deterministic job workspaces, stage checkpoints, exports, and delivery receipts |
| `artcraft_verify_edit` | Yes | Yes | Verification | Verify output validity, dimensions, and pixel diff (full image or `[x, y, w, h]` region) |
| `photocraft_run` | Yes | — | PhotoCraft | Show `photocraft-cli` help or version |
| `lightcraft_run` | Yes | — | LightCraft | Show `lightcraft-cli` help or version |

## CLI Subcommands

```bash
hermes artcraft doctor
hermes artcraft inspect <path> [--working-dir DIR] [--preview-max DIM] [--crop-size SIZE]
hermes artcraft develop <input_path> <output_path> [--set KEY=VALUE ...] [--preset ID] [--size PX] [--quality 1..100]
hermes artcraft audio info <input_path>
hermes artcraft audio convert <input_path> <output_path> [--rate HZ] [--bit-depth 16|24|32f] [--normalize] [--dither|--no-dither]
hermes artcraft video probe <input_path>
hermes artcraft video render-frame <input_path> <output_path> [--seconds SEC] [--scale SCALE]
hermes artcraft video export <input_path> <output_path> [--start SEC] [--end SEC] [--format FMT] [--preset ID] [--scale SCALE]
hermes artcraft prep-print <input_path> <output_path> --width W --height H [--ppi PPI] [--fit-mode MODE] [--confirm-crop]
hermes artcraft restore <recipe> <input_path> <output_path> [--params JSON] [--region X Y W H] [--checkpoint-dir DIR]
hermes artcraft checkpoint {list,get} <checkpoint_dir> [--step-id ID]
hermes artcraft review <source_path> <output_path> [--working-dir DIR] [--region X Y W H] [--no-preserve-framing] [--crop-geometry JSON]
hermes artcraft job {create,status,checkpoint,record-export,record-delivery,reconcile,resume} ...
hermes artcraft verify <input_path> <output_path> [--width W] [--height H] [--region X Y W H]
```

Or standalone without Hermes:
```bash
python3 -m artcraft_plugin.cli doctor
python3 -m artcraft_plugin.cli inspect input.png --preview-max 1024 --crop-size 256
python3 -m artcraft_plugin.cli develop input.png developed.jpg --set light.exposure=0.3 --size 2048 --quality 92
python3 -m artcraft_plugin.cli audio info dialogue.wav
python3 -m artcraft_plugin.cli audio convert dialogue.wav dialogue_48k.wav --rate 48000 --bit-depth 24 --normalize
python3 -m artcraft_plugin.cli video probe clip.mp4
python3 -m artcraft_plugin.cli video render-frame clip.mp4 frame.png --seconds 1.5
python3 -m artcraft_plugin.cli video export clip.mp4 trim.mp4 --start 0.5 --end 4.0 --format mp4
python3 -m artcraft_plugin.cli prep-print input.png output.png --width 8 --height 10 --fit-mode margins
python3 -m artcraft_plugin.cli restore faded_tones input.png output.png --params '{"in_black": 15, "in_white": 240}'
python3 -m artcraft_plugin.cli checkpoint list ./checkpoints
python3 -m artcraft_plugin.cli verify input.png output.png --region 100 100 64 64
```

### Intentional Crop Review

For an intentional crop, pass the editor's retained boundary to `review`. The comparison shades the removed area on the source and shows the output beside it:

```sh
hermes artcraft review source.jpg cropped.jpg --no-preserve-framing \
  --crop-geometry '{"rect":[55,106,1745,2409]}'
```

The agent tool (`artcraft_build_review`) accepts the same object as `crop_geometry`. Coordinates are in source image pixels with origin at the upper left. Use `quad` with four perimeter-ordered points for a perspective crop. On a straightened image, a rectangle can include `artwork_rect` and a calibrated `pixels_per_inch` to report paint trim per edge. Without calibration, the trim is unmeasured. Review the comparison to assess composition and signature retention.

## Bundled Skills (`skills/`)

All 15 bundled `SKILL.md` files comply with Hermes skill authoring standards:

- `artcraft-router` — Route creative media tasks across the ArtCraft CLI suite.
- `lightcraft-basics` — Develop and render photos non-destructively.
- `soundcraft-basics` — Inspect, convert, resample, and normalize audio files.
- `filmcraft-basics` — Probe media, extract still frames, and export video clips.
- `photo-inspection` — Generate whole-photo previews, native crops, and metrics.
- `photo-restoration` — Run checkpointed photo repairs with visual review gates.
- `print-preparation` — Format print-ready images with aspect and PPI checks.
- `photocraft-cli-edits` — Apply localized spot healing with pixel-diff verification.
- `lightcraft-cli-edits` — Inspect LightCraft CLI flags and verify exported images.
- `recipe-faded-tones` — Restore compressed tonal range without clipping endpoints.
- `recipe-color-cast` — Remove unwanted color tints while preserving skin tones.
- `recipe-dust-scratches` — Heal isolated dust specks and scratches without blurring.
- `recipe-noise-grain` — Reduce sensor and scan noise while retaining fine detail.
- `recipe-sharpening` — Apply restrained unsharp masking without edge halos.
- `recipe-enlargement` — Upscale images proportionally with restrained sharpening.

## Development

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT
