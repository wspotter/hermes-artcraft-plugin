"""JSON tool schemas for the Hermes ArtCraft plugin."""

ARTCRAFT_STATUS = {
    "name": "artcraft_status",
    "description": (
        "Discover installed ArtCraft CLI binaries (photocraft-cli, lightcraft-cli, "
        "filmcraft-cli, soundcraft-cli) and report their paths and versions."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

ARTCRAFT_INSPECT = {
    "name": "artcraft_inspect",
    "description": (
        "Inspect an image file and return its format, color mode, width, height, DPI, "
        "byte size, and SHA-256 hash."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the image file to inspect.",
            },
        },
        "required": ["path"],
    },
}

ARTCRAFT_PREPARE_INSPECTION = {
    "name": "artcraft_prepare_inspection",
    "description": (
        "Prepare an image for agent visual inspection: generates a whole-photo preview "
        "and 1:1 native-resolution crops into a working directory without altering the "
        "source file. Computes orientation, color profile, effective print resolution (PPI), "
        "and measured clues (endpoint clipping, sharpness, noise) with explicit measurement limits."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the image file to inspect.",
            },
            "working_dir": {
                "type": "string",
                "description": "Directory to write preview and crops into. Created if missing. Defaults to a temp directory.",
            },
            "max_preview_dimension": {
                "type": "integer",
                "description": "Maximum width/height of the generated preview image (default 1024).",
                "minimum": 64,
                "maximum": 4096,
            },
            "crop_size": {
                "type": "integer",
                "description": "Pixel width/height of default native crops (default 256).",
                "minimum": 16,
                "maximum": 2048,
            },
            "regions": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "description": "Optional list of custom crop regions [x, y, width, height] in source pixels.",
            },
            "target_print_sizes": {
                "type": "array",
                "description": "Optional custom target print sizes to compute effective PPI for (e.g. [[8, 10], [11, 14]]).",
            },
        },
        "required": ["path"],
    },
}

ARTCRAFT_VERIFY_EDIT = {
    "name": "artcraft_verify_edit",
    "description": (
        "Verify an edited image against its source input. Checks that the output is a "
        "valid image, optionally matches expected dimensions, and has non-zero pixel "
        "changes (catching silent no-op edits)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the original source image.",
            },
            "output_path": {
                "type": "string",
                "description": "Path to the edited output image.",
            },
            "expected_width": {
                "type": "integer",
                "description": "Optional expected output width in pixels.",
            },
            "expected_height": {
                "type": "integer",
                "description": "Optional expected output height in pixels.",
            },
            "region": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Optional [x, y, width, height] region that must show pixel changes.",
            },
            "require_pixel_change": {
                "type": "boolean",
                "description": "Fail verification if output is pixel-identical to input (default true).",
            },
        },
        "required": ["input_path", "output_path"],
    },
}

def _cli_probe_schema(app):
    return {
        "name": f"{app}_run",
        "description": f"Show {app}-cli help or version.",
        "parameters": {
            "type": "object",
            "properties": {"cli_args": {
                "type": "array", "items": {"enum": ["--help", "--version"]},
                "minItems": 1, "maxItems": 1,
            }},
            "required": ["cli_args"],
        },
    }


PHOTOCRAFT_RUN = _cli_probe_schema("photocraft")
LIGHTCRAFT_RUN = _cli_probe_schema("lightcraft")

PHOTOCRAFT_SPOT_HEAL = {
    "name": "photocraft_spot_heal",
    "description": "Heal a visible scratch or blemish and save a verified new PNG.",
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {"type": "string"},
            "output_path": {"type": "string", "description": "New PNG path."},
            "points": {"type": "array", "items": {
                "type": "array", "items": {"type": "integer"},
                "minItems": 2, "maxItems": 2,
            }, "description": "Stroke points in source pixel coordinates."},
            "size": {"type": "integer", "minimum": 1, "maximum": 256},
            "region": {"type": "array", "items": {"type": "integer"},
                       "minItems": 4, "maxItems": 4,
                       "description": "[x, y, width, height] covering the allowed edit including brush edges."},
            "timeout_s": {
                "type": "number",
                "description": "Optional execution timeout in seconds (default 120.0).",
            },
        },
        "required": ["input_path", "output_path", "points", "size", "region"],
    },
}

ARTCRAFT_PREPARE_PRINT = {
    "name": "artcraft_prepare_print",
    "description": (
        "Prepare an agreed print request into a correctly sized, verified delivery file. "
        "Calculates required pixels from physical dimensions (width_in, height_in) and PPI, "
        "compares aspect ratios, enforces a clarification gate when instructions conflict "
        "between borderless crop and margins, strictly preserves proportions, reports effective "
        "source resolution separately from export resolution, preserves ICC color profiles, "
        "reopens and decodes the delivery file to verify dimensions, PPI, format, and profile, "
        "and produces a visual composition preview."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the source photo.",
            },
            "output_path": {
                "type": "string",
                "description": "Path for the prepared print delivery file.",
            },
            "width_in": {
                "type": "number",
                "description": "Print target width in inches (e.g. 8.0).",
            },
            "height_in": {
                "type": "number",
                "description": "Print target height in inches (e.g. 10.0).",
            },
            "orientation": {
                "type": "string",
                "enum": ["auto", "portrait", "landscape"],
                "default": "auto",
                "description": "Target print orientation (default 'auto').",
            },
            "fit_mode": {
                "type": "string",
                "enum": ["auto", "borderless", "crop", "margins", "fit"],
                "default": "auto",
                "description": "Fit mode: 'borderless'/'crop' to fill sheet; 'margins'/'fit' to preserve entire photo with margins.",
            },
            "confirm_crop": {
                "type": "boolean",
                "default": False,
                "description": "Confirm cropping when aspect ratio conflicts with sheet in borderless mode.",
            },
            "ppi": {
                "type": "integer",
                "default": 300,
                "description": "Target export resolution in pixels per inch (default 300).",
            },
            "output_format": {
                "type": "string",
                "enum": ["auto", "PNG", "TIFF", "JPEG"],
                "default": "auto",
                "description": "Output image format (default auto, inferred from output_path).",
            },
            "margin_color": {
                "type": "string",
                "default": "white",
                "description": "Color for margins when fit_mode is margins (default 'white').",
            },
            "preserve_master_path": {
                "type": "string",
                "description": "Optional destination path to preserve an untouched master copy.",
            },
            "allow_upscale": {
                "type": "boolean",
                "default": False,
                "description": "Allow upscaling if source image resolution is smaller than target print pixels.",
            },
            "target_icc": {
                "type": "string",
                "description": "Optional path to target ICC profile or 'sRGB'.",
            },
            "preview_path": {
                "type": "string",
                "description": "Optional explicit path to save the verification preview.",
            },
        },
        "required": ["input_path", "output_path", "width_in", "height_in"],
    },
}

ARTCRAFT_RESTORE_STEP = {
    "name": "artcraft_restore_step",
    "description": (
        "Apply a verified restoration recipe to an aged or damaged photograph: "
        "faded_tones, color_cast, dust_and_scratches, noise_and_grain, sharpening, enlargement. "
        "Stores a checkpoint and native-resolution comparison crops before and after the step. "
        "Enforces the Stop/Ask Gate: refuses destructive operations and hallucinated reconstructions "
        "without explicit approval."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the input photo (or previous checkpoint).",
            },
            "output_path": {
                "type": "string",
                "description": "Path to write the restored output photo.",
            },
            "recipe": {
                "type": "string",
                "enum": [
                    "faded_tones",
                    "color_cast",
                    "dust_and_scratches",
                    "noise_and_grain",
                    "sharpening",
                    "enlargement",
                ],
                "description": "Restoration recipe name.",
            },
            "parameters": {
                "type": "object",
                "description": "Optional recipe parameters (e.g. contrast, shadow_lift, color_temp, noise_strength, radius).",
            },
            "region": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Optional [x, y, width, height] region for localized healing or crop focus.",
            },
            "checkpoint_dir": {
                "type": "string",
                "description": "Directory to store checkpoint manifest and comparison crops.",
            },
            "step_name": {
                "type": "string",
                "description": "Optional custom name for this checkpoint step (e.g. '01_faded_tones').",
            },
            "crop_regions": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "description": "Optional list of [x, y, w, h] regions for before/after comparison crops.",
            },
            "target_print_ppi": {
                "type": "integer",
                "default": 300,
                "description": "Target print resolution in PPI for simulated print-scale crops (default 300).",
            },
            "reconstruct_missing": {
                "type": "boolean",
                "default": False,
                "description": "Set true if request requires reconstructing missing features (triggers Stop/Ask Gate).",
            },
            "content_type": {
                "type": "string",
                "description": "Content type hint (e.g. 'missing_face', 'missing_lettering'). Triggers Stop/Ask Gate.",
            },
            "allow_overwrite": {
                "type": "boolean",
                "default": False,
                "description": "Allow overwriting output_path if it already exists.",
            },
            "timeout_s": {
                "type": "number",
                "default": 120.0,
                "description": "CLI timeout in seconds.",
            },
        },
        "required": ["input_path", "output_path", "recipe"],
    },
}

ARTCRAFT_CHECKPOINT = {
    "name": "artcraft_checkpoint",
    "description": "Inspect and list restoration checkpoints and comparison crops for a restoration session.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "get"],
                "description": "Action to perform: 'list' all checkpoints or 'get' details for one step.",
            },
            "checkpoint_dir": {
                "type": "string",
                "description": "Path to the checkpoint directory containing manifest.json.",
            },
            "step_identifier": {
                "description": "Step index (integer) or step name (string) when action is 'get'.",
            },
        },
        "required": ["action", "checkpoint_dir"],
    },
}

ARTCRAFT_BUILD_REVIEW = {
    "name": "artcraft_build_review",
    "description": (
        "Build a structured review package for an image edit: whole-photo before/after previews, "
        "native-resolution repaired-area crops with local texture variance metrics, source/output hashes, "
        "mechanical checks (dimensions, aspect ratio, format, ICC), concise summary of changes & concerns, "
        "and automated defect detection flags: untouched scratch / no-op (0 changed pixels), unwanted crop "
        "(unexpected aspect or framing change), and smeared repair (>80% variance collapse). "
        "Supports bounded retry tracking (retry_count, max_retries, last_checkpoint_path)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source_path": {"type": "string", "description": "Original source image path."},
            "output_path": {"type": "string", "description": "Edited/repaired output image path."},
            "regions": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                "description": "Optional list of target repair regions [x, y, width, height] in source pixels.",
            },
            "region": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4,
                "description": "Optional single repair region [x, y, width, height].",
            },
            "working_dir": {"type": "string", "description": "Optional directory to store previews and crops."},
            "max_preview_dimension": {"type": "integer", "default": 1024, "description": "Max preview size in px."},
            "crop_size": {"type": "integer", "default": 256, "description": "Native crop dimension in px."},
            "expected_aspect": {"type": "string", "description": "Optional expected aspect ratio (e.g. '4:5' or 0.8)."},
            "crop_geometry": {"type": "object", "description": "Editor-supplied source pixel geometry: rect [left,top,right,bottom] or quad of four ordered [x,y] points. For a rect on a straightened source, optional artwork_rect and pixels_per_inch measure paint trim."},
            "preserve_framing": {"type": "boolean", "default": True, "description": "Whether framing/aspect must match source unless authorized."},
            "retry_count": {"type": "integer", "default": 0, "description": "Current retry attempt index."},
            "max_retries": {"type": "integer", "default": 3, "description": "Maximum allowed retry attempts."},
            "last_checkpoint_path": {"type": "string", "description": "Path to last known good checkpoint to resume from on failure."},
        },
        "required": ["source_path", "output_path"],
    },
}

ARTCRAFT_JOB = {
    "name": "artcraft_job",
    "description": (
        "Manage deterministic ArtCraft job workspaces (source/, work/, previews/, exports/, job.json). "
        "Supports creating/initializing jobs, saving checkpoints, resuming from the last verified checkpoint, "
        "recording verified export artifacts, recording delivery receipts, preventing duplicate deliveries of "
        "the same hash to the same destination, and reconciling uncertain delivery receipts before retrying."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["init", "checkpoint", "resume", "export", "deliver", "reconcile", "status"],
                "description": "Job action to perform.",
            },
            "job_id": {"type": "string", "description": "Unique job identifier."},
            "workspace_dir": {"type": "string", "description": "Optional base workspace directory."},
            "source_path": {"type": "string", "description": "Source image path (used with 'init')."},
            "stage": {"type": "string", "description": "Stage name for checkpoint (e.g. 'spot_heal', 'print_prep')."},
            "file_path": {"type": "string", "description": "File path for checkpoint or export artifact."},
            "verified": {"type": "boolean", "default": True, "description": "Whether checkpoint or artifact is verified (default true)."},
            "artifact_id": {"type": "string", "description": "Artifact identifier for export or delivery."},
            "destination": {"type": "string", "description": "Destination file path or URI for delivery or reconciliation."},
            "status": {
                "type": "string",
                "enum": ["pending", "delivered", "uncertain", "failed"],
                "description": "Delivery status (default 'pending' for deliver; or 'delivered'/'failed' for reconcile).",
            },
            "receipt_id": {"type": "string", "description": "Optional delivery receipt ID for reconcile."},
            "notes": {"type": "string", "description": "Optional notes or reason for delivery/reconciliation."},
            "metadata": {"type": "object", "description": "Optional arbitrary metadata dict."},
        },
        "required": ["action", "job_id"],
    },
}

ARTCRAFT_DEVELOP = {
    "name": "artcraft_develop",
    "description": (
        "Develop and export an image or raw file non-destructively via LightCraft (`lightcraft-cli render`). "
        "Supports develop sliders (`light.exposure`, `light.contrast`, `color.temp`, `color.vibrance`, "
        "`detail.sharpening`, etc.), presets, long-edge resize, quality, and export options while verifying "
        "that source_sha256 is unchanged and the output image decodes cleanly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "input_path": {
                "type": "string",
                "description": "Path to the source image or raw file.",
            },
            "output_path": {
                "type": "string",
                "description": "Path for the developed output file (.jpg, .png, .tif, .webp, .avif, .jxl, .dng).",
            },
            "sliders": {
                "type": "object",
                "description": "Optional dict of develop control IDs to values (e.g. {'light.exposure': 0.5, 'light.contrast': 10}).",
            },
            "preset": {
                "type": "string",
                "description": "Optional LightCraft preset ID to apply.",
            },
            "long_edge": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional output long edge in pixels.",
            },
            "quality": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 92,
                "description": "Export quality 1..100 for lossy formats (default 92).",
            },
            "export_options": {
                "type": "object",
                "description": "Optional dict of LightCraft app.export options (e.g. {'colorSpace': 'displayP3', 'ppi': 300}).",
            },
            "allow_overwrite": {
                "type": "boolean",
                "default": False,
                "description": "Allow overwriting output_path if it already exists (default false).",
            },
            "timeout_s": {
                "type": "number",
                "default": 120.0,
                "description": "Optional execution timeout in seconds (default 120.0).",
            },
        },
        "required": ["input_path", "output_path"],
    },
}

ARTCRAFT_AUDIO_BASIC = {
    "name": "artcraft_audio_basic",
    "description": (
        "Inspect audio metadata (`action='info'`) or non-destructively convert, resample, change bit depth, "
        "and peak-normalize audio files (`action='convert'`) via SoundCraft (`soundcraft-cli`)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["info", "convert"],
                "description": "Audio operation: 'info' to probe metadata or 'convert' to write a converted audio file.",
            },
            "input_path": {
                "type": "string",
                "description": "Path to the source audio file.",
            },
            "output_path": {
                "type": "string",
                "description": "Destination audio file path (required when action='convert').",
            },
            "sample_rate": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional target sample rate in Hz (e.g. 44100, 48000).",
            },
            "bit_depth": {
                "type": "string",
                "enum": ["16", "24", "32f"],
                "description": "Optional output bit depth ('16', '24', or '32f').",
            },
            "normalize": {
                "type": "boolean",
                "default": False,
                "description": "Normalize peak amplitude to -0.1 dBFS when converting (default false).",
            },
            "dither": {
                "type": "boolean",
                "description": "Optional explicit dithering toggle (true for --dither, false for --no-dither).",
            },
            "allow_overwrite": {
                "type": "boolean",
                "default": False,
                "description": "Allow overwriting output_path if it already exists (default false).",
            },
            "timeout_s": {
                "type": "number",
                "default": 120.0,
                "description": "Optional execution timeout in seconds (default 120.0).",
            },
        },
        "required": ["action", "input_path"],
    },
}

ARTCRAFT_VIDEO_BASIC = {
    "name": "artcraft_video_basic",
    "description": (
        "Probe media containers/streams (`action='probe'`), extract a verified PNG still frame "
        "(`action='render_frame'`), or non-destructively trim/transcode/export video (`action='export'`) "
        "via FilmCraft (`filmcraft-cli`)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["probe", "render_frame", "export"],
                "description": "Video operation: 'probe', 'render_frame', or 'export'.",
            },
            "input_path": {
                "type": "string",
                "description": "Path to a standalone media file (required for 'probe'; optional source for 'render_frame'/'export').",
            },
            "project_path": {
                "type": "string",
                "description": "Optional path to a FilmCraft project (.fcproj) for 'render_frame' or 'export'.",
            },
            "demo": {
                "type": "boolean",
                "default": False,
                "description": "Use the built-in FilmCraft procedural demo project (default false).",
            },
            "output_path": {
                "type": "string",
                "description": "Destination file path (required for 'render_frame' and 'export').",
            },
            "seconds": {
                "type": "number",
                "default": 0.0,
                "description": "Timestamp in seconds for 'render_frame' (default 0.0).",
            },
            "start_seconds": {
                "type": "number",
                "description": "Optional custom range start time in seconds for 'export'.",
            },
            "end_seconds": {
                "type": "number",
                "description": "Optional custom range end time in seconds for 'export'.",
            },
            "format": {
                "type": "string",
                "description": "Optional export format override (e.g. 'h264', 'hevc', 'prores', 'wav', 'mp3').",
            },
            "preset": {
                "type": "string",
                "description": "Optional FilmCraft export preset name.",
            },
            "scale": {
                "type": "number",
                "description": "Optional frame scale factor (e.g. 0.5 for half resolution).",
            },
            "quality": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Optional export quality (0..100).",
            },
            "no_audio": {
                "type": "boolean",
                "default": False,
                "description": "Omit audio streams when exporting (default false).",
            },
            "allow_overwrite": {
                "type": "boolean",
                "default": False,
                "description": "Allow overwriting output_path if it already exists (default false).",
            },
            "timeout_s": {
                "type": "number",
                "default": 180.0,
                "description": "Optional execution timeout in seconds (default 180.0).",
            },
        },
        "required": ["action"],
    },
}



