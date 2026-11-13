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


def spot_heal(input_path: str, output_path: str, points: list, size: int, region: list) -> dict:
    """Heal a visible defect and publish a new PNG only after verification."""
    import json
    import os
    import shutil
    from tempfile import TemporaryDirectory

    from .verify import _validate_region, inspect_image, sha256_file

    source = Path(input_path).expanduser().resolve(strict=True)
    target = Path(output_path).expanduser().absolute()
    if target.suffix.lower() != ".png" or os.path.lexists(target):
        raise ValueError("output_path must name a new PNG in an existing directory")
    info = inspect_image(str(source))
    if not info.get("valid"):
        raise ValueError("input_path must be a readable image")
    if not isinstance(region, list) or any(type(v) is not int for v in region):
        raise ValueError("region must contain four integer coordinates")
    left, top, right, bottom = _validate_region(region, info["width"], info["height"])
    if type(size) is not int or not 1 <= size <= 256:
        raise ValueError("size must be an integer between 1 and 256")
    if not isinstance(points, list) or not 1 <= len(points) <= 512:
        raise ValueError("provide 1 to 512 stroke points")
    for point in points:
        if (
            not isinstance(point, list)
            or len(point) != 2
            or any(type(v) is not int for v in point)
            or not (left <= point[0] < right and top <= point[1] < bottom)
        ):
            raise ValueError("stroke points must be integer [x, y] pairs inside region")

    with TemporaryDirectory(prefix=".artcraft-", dir=target.parent) as directory:
        work = Path(directory) / ("source" + source.suffix)
        output = Path(directory) / "healed.png"
        shutil.copyfile(source, work)
        if sha256_file(work) != info["sha256"]:
            raise ValueError("source changed while staging")
        result = run_artcraft_cli(
            "photocraft",
            ["run", str(work), "--cmd", "paint.spotHealing", "--params",
             json.dumps({"points": points, "size": size}), "--out", str(output)],
            input_path=str(source), output_path=str(output),
            expected_width=info["width"], expected_height=info["height"], region=region,
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"], "stderr": result.get("stderr", "")[-1000:]}
        verification = result["verification"]
        diff = verification["pixel_diff"]
        outside = diff["changed_pixels"] - diff["region"]["changed_pixels"]
        if outside:
            return {"ok": False, "error": "pixels_changed_outside_region", "outside_pixels": outside}
        if sha256_file(source) != info["sha256"]:
            raise ValueError("source changed during the edit")
        if verification["output"]["format"] != "PNG":
            raise ValueError("PhotoCraft did not produce a PNG")
        os.link(output, target)
        return {
            "ok": True, "output_path": str(target), "source_sha256": info["sha256"],
            "output_sha256": verification["output"]["sha256"],
            "region": region, "changed_pixels": diff["changed_pixels"], "outside_pixels": 0,
        }
