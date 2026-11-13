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

_CLI_RUN_PROPERTIES = {
    "cli_args": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Arguments to pass directly to the CLI executable.",
    },
    "input_path": {
        "type": "string",
        "description": "Source image path (used for non-destructive guard and post-edit verification).",
    },
    "output_path": {
        "type": "string",
        "description": "Target output path (must differ from input_path).",
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
        "description": "Optional [x, y, width, height] region to verify pixel changes.",
    },
    "verify": {
        "type": "boolean",
        "description": "Run automatic post-edit verification when input_path and output_path are set (default true).",
    },
    "timeout_s": {
        "type": "number",
        "description": "Command timeout in seconds (default 120).",
    },
}

PHOTOCRAFT_RUN = {
    "name": "photocraft_run",
    "description": (
        "Run photocraft-cli with non-destructive output guards and automatic post-edit "
        "pixel-diff verification."
    ),
    "parameters": {
        "type": "object",
        "properties": _CLI_RUN_PROPERTIES,
        "required": ["cli_args"],
    },
}

LIGHTCRAFT_RUN = {
    "name": "lightcraft_run",
    "description": (
        "Run lightcraft-cli with non-destructive output guards and automatic post-edit "
        "pixel-diff verification."
    ),
    "parameters": {
        "type": "object",
        "properties": _CLI_RUN_PROPERTIES,
        "required": ["cli_args"],
    },
}
