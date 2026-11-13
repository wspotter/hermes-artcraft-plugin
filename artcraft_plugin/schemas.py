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
