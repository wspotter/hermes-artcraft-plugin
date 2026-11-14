"""Standard I/O Model Context Protocol (MCP) server for ArtCraft tools.

Lightweight, zero-extra-dependency JSON-RPC 2.0 stdio server enabling
MCP clients to access ArtCraft image inspection, print preparation,
verified spot-healing, step checkpoints, review packages, job workspaces,
and non-destructive basics across PhotoCraft, LightCraft, FilmCraft, and SoundCraft.
"""

from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO, Callable, Dict, Optional

from . import schemas, tools

# Registry of tools exposed over MCP
EXPOSED_TOOLS: Dict[str, Dict[str, Any]] = {
    "artcraft_status": {
        "schema": schemas.ARTCRAFT_STATUS,
        "handler": tools.artcraft_status,
    },
    "artcraft_inspect": {
        "schema": schemas.ARTCRAFT_INSPECT,
        "handler": tools.artcraft_inspect,
    },
    "artcraft_prepare_inspection": {
        "schema": schemas.ARTCRAFT_PREPARE_INSPECTION,
        "handler": tools.artcraft_prepare_inspection,
    },
    "artcraft_prepare_print": {
        "schema": schemas.ARTCRAFT_PREPARE_PRINT,
        "handler": tools.artcraft_prepare_print,
    },
    "artcraft_verify_edit": {
        "schema": schemas.ARTCRAFT_VERIFY_EDIT,
        "handler": tools.artcraft_verify_edit,
    },
    "photocraft_spot_heal": {
        "schema": schemas.PHOTOCRAFT_SPOT_HEAL,
        "handler": tools.photocraft_spot_heal,
    },
    "artcraft_restore_step": {
        "schema": schemas.ARTCRAFT_RESTORE_STEP,
        "handler": tools.artcraft_restore_step,
    },
    "artcraft_checkpoint": {
        "schema": schemas.ARTCRAFT_CHECKPOINT,
        "handler": tools.artcraft_checkpoint,
    },
    "artcraft_build_review": {
        "schema": schemas.ARTCRAFT_BUILD_REVIEW,
        "handler": tools.artcraft_build_review,
    },
    "artcraft_job": {
        "schema": schemas.ARTCRAFT_JOB,
        "handler": tools.artcraft_job,
    },
    "artcraft_develop": {
        "schema": schemas.ARTCRAFT_DEVELOP,
        "handler": tools.artcraft_develop,
    },
    "artcraft_audio_basic": {
        "schema": schemas.ARTCRAFT_AUDIO_BASIC,
        "handler": tools.artcraft_audio_basic,
    },
    "artcraft_video_basic": {
        "schema": schemas.ARTCRAFT_VIDEO_BASIC,
        "handler": tools.artcraft_video_basic,
    },
}


def read_message(stream: BinaryIO = sys.stdin.buffer) -> Optional[Dict[str, Any]]:
    """Read a JSON-RPC message from stream supporting newline-delimited or Content-Length framing."""
    line = stream.readline(1_000_000)
    if not line:
        return None

    line_stripped = line.strip()
    if not line_stripped:
        return None

    if line_stripped.startswith(b"{"):
        try:
            val = json.loads(line_stripped.decode("utf-8"))
            return val if isinstance(val, dict) else None
        except Exception:
            return None

    if line_stripped.lower().startswith(b"content-length:"):
        try:
            parts = line_stripped.split(b":", 1)
            length = int(parts[1].strip())
            # Consume any trailing header lines until blank line
            while True:
                hdr = stream.readline(10_000)
                if not hdr or hdr in (b"\r\n", b"\n", b""):
                    break
            body = stream.read(length)
            val = json.loads(body.decode("utf-8"))
            return val if isinstance(val, dict) else None
        except Exception:
            return None

    return None


def send_message(message: Dict[str, Any], stream: BinaryIO = sys.stdout.buffer) -> None:
    """Send a JSON-RPC message newline-delimited to output stream."""
    data = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    stream.write(data)
    stream.flush()


def _result_is_error(tool_name: str, result_str: str) -> bool:
    """Return True when a JSON tool payload represents an execution/validation failure.

    Preserves isError=False for interactive clarification/decision gates and
    for successful quality-assessment tools (`artcraft_build_review`,
    `artcraft_verify_edit`) when they cleanly reject an image's quality without
    an execution error.
    """
    try:
        data = json.loads(result_str)
    except Exception:
        return False

    if not isinstance(data, dict):
        return False

    if data.get("status") in ("needs_clarification", "needs_decision"):
        return False

    if data.get("ok") is False:
        return True

    if data.get("error"):
        return True

    if tool_name == "artcraft_verify_edit" and data.get("passed") is False:
        reason = str(data.get("reason") or "")
        if reason.startswith(("invalid_input", "invalid_output")):
            return True

    return False


def process_message(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single JSON-RPC 2.0 request or notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return None

    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    # Notifications do not return a response
    if method == "notifications/initialized" or (method and request_id is None):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "artcraft-plugin",
                    "version": "0.2.0",
                },
                "instructions": (
                    "ArtCraft photo inspection, print prep, verified spot-healing, "
                    "LightCraft photo development, SoundCraft audio basics, "
                    "FilmCraft video basics, step checkpoints, review packages, "
                    "and job workspaces."
                ),
            },
        }

    if method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {},
        }

    if method == "tools/list":
        tools_list = []
        for name, meta in EXPOSED_TOOLS.items():
            schema = meta["schema"]
            tools_list.append({
                "name": name,
                "description": schema.get("description", ""),
                "inputSchema": schema.get("parameters", {"type": "object", "properties": {}}),
            })
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools_list,
            },
        }

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}

        if tool_name not in EXPOSED_TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Unknown ArtCraft tool: {tool_name}"}
                    ],
                    "isError": True,
                },
            }

        handler: Callable[..., str] = EXPOSED_TOOLS[tool_name]["handler"]
        try:
            result_str = handler(arguments)
            is_error = _result_is_error(tool_name, result_str)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": result_str}
                    ],
                    "isError": is_error,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Error executing {tool_name}: {exc}"}
                    ],
                    "isError": True,
                },
            }

    if request_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}",
            },
        }

    return None


def run_server(in_stream: BinaryIO = sys.stdin.buffer, out_stream: BinaryIO = sys.stdout.buffer) -> None:
    """Run the stdio message processing loop until EOF."""
    while True:
        msg = read_message(in_stream)
        if msg is None:
            # Check if end of stream reached
            # In BinaryIO, read of 0 bytes or empty indicates EOF
            break
        resp = process_message(msg)
        if resp is not None:
            send_message(resp, out_stream)


def main() -> None:
    """CLI entrypoint for running the MCP server."""
    run_server()


if __name__ == "__main__":
    main()
