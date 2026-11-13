"""Safe CLI execution wrapper for ArtCraft apps."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .discovery import find_cli_binary
from .verify import verify_edit


def _paths_refer_to_same_file(path_a: Path, path_b: Path) -> bool:
    """Return True when two paths resolve to the same target location."""
    return path_a.expanduser().resolve() == path_b.expanduser().resolve()


def run_artcraft_cli(
    app: str,
    cli_args: Sequence[str],
    *,
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
    expected_width: Optional[int] = None,
    expected_height: Optional[int] = None,
    region: Optional[Sequence[int]] = None,
    verify: bool = True,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Execute an ArtCraft CLI command with non-destructive guards and optional verification."""
    binary = find_cli_binary(app)
    if binary is None:
        return {
            "ok": False,
            "error": f"{app}-cli binary not found on PATH or standard ArtCraft locations",
        }

    if input_path and output_path and _paths_refer_to_same_file(Path(input_path), Path(output_path)):
        return {
            "ok": False,
            "error": "non_destructive_guard: output_path must be distinct from input_path",
        }

    if output_path:
        Path(output_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    cmd: List[str] = [str(binary), *[str(a) for a in cli_args]]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "command": cmd,
            "error": f"timeout: {binary.name} exceeded {timeout_s}s",
        }
    except Exception as exc:
        return {
            "ok": False,
            "command": cmd,
            "error": f"execution_failed: {exc}",
        }

    result: Dict[str, Any] = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": cmd,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    if proc.returncode != 0:
        result["error"] = f"{binary.name} exited with code {proc.returncode}"
        return result

    if verify and input_path and output_path:
        verification = verify_edit(
            input_path,
            output_path,
            expected_width=expected_width,
            expected_height=expected_height,
            region=region,
        )
        result["verification"] = verification
        if not verification.get("passed"):
            result["ok"] = False
            result["error"] = verification.get("reason", "verification_failed")

    return result
