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

