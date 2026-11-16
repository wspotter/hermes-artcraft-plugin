"""Verified, non-destructive basic CLI wrappers for LightCraft, SoundCraft, and FilmCraft."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional

from PIL import Image

from .discovery import find_cli_binary
from .runner import _paths_refer_to_same_file, atomic_replace_file
from .verify import inspect_image, sha256_file

FILMCRAFT_TICKS_PER_SECOND = 254_016_000_000


def _atomic_promote(src: Path, dst: Path, *, allow_overwrite: bool = False) -> None:
    """Atomically promote a verified temporary output file to dst."""
    atomic_replace_file(src, dst, allow_overwrite=allow_overwrite)


def lightcraft_develop(
    input_path: str,
    output_path: str,
    *,
    sliders: Optional[Dict[str, Any]] = None,
    preset: Optional[str] = None,
    long_edge: Optional[int] = None,
    quality: int = 92,
    export_options: Optional[Dict[str, Any]] = None,
    allow_overwrite: bool = False,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Develop an image or raw file via `lightcraft-cli render` non-destructively."""
    src_path = Path(input_path).expanduser()
    out_path = Path(output_path).expanduser()

    if not src_path.is_file():
        return {"ok": False, "app": "lightcraft", "error": f"Input file does not exist: {src_path}"}

    if _paths_refer_to_same_file(src_path, out_path):
        return {
            "ok": False,
            "app": "lightcraft",
            "error": "non_destructive_guard: output_path must be distinct from input_path",
        }

    if os.path.lexists(out_path) and not allow_overwrite:
        return {
            "ok": False,
            "app": "lightcraft",
            "error": (
                f"Output file already exists: {out_path} "
                "(set allow_overwrite=True to overwrite)"
            ),
        }

    binary = find_cli_binary("lightcraft")
    if binary is None:
        return {
            "ok": False,
            "app": "lightcraft",
            "error": "lightcraft-cli binary not found on PATH or standard ArtCraft locations",
        }

    source_sha256 = sha256_file(src_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_path.suffix or ".jpg"

    with TemporaryDirectory(prefix=".artcraft-lc-", dir=out_path.parent) as tmp_dir:
        tmp_out = Path(tmp_dir) / f"developed{suffix}"
        cmd: List[str] = [str(binary), "render", str(src_path), "-o", str(tmp_out)]

        if preset:
            cmd.extend(["--preset", str(preset)])

        if sliders:
            for k, v in sliders.items():
                cmd.extend(["--set", f"{k}={v}"])

        if long_edge is not None:
            if int(long_edge) <= 0:
                return {
                    "ok": False,
                    "app": "lightcraft",
                    "error": "long_edge must be a positive integer",
                }
            cmd.extend(["--size", str(int(long_edge))])

        if quality is not None:
            q_int = int(quality)
            if not 1 <= q_int <= 100:
                return {
                    "ok": False,
                    "app": "lightcraft",
                    "error": "quality must be between 1 and 100",
                }
            cmd.extend(["--quality", str(q_int)])

        if export_options:
            for k, v in export_options.items():
                val_str = json.dumps(v) if isinstance(v, (bool, list, dict)) else str(v)
                cmd.extend(["--opt", f"{k}={val_str}"])

        t0 = time.monotonic()
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
                "app": "lightcraft",
                "command": cmd,
                "error": f"timeout: lightcraft-cli exceeded {timeout_s}s",
            }
        except Exception as exc:
            return {
                "ok": False,
                "app": "lightcraft",
                "command": cmd,
                "error": f"execution_failed: {exc}",
            }
        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)

        if proc.returncode != 0:
            return {
                "ok": False,
                "app": "lightcraft",
                "command": cmd,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "error": f"lightcraft-cli exited with code {proc.returncode}",
            }

        if not tmp_out.is_file() or tmp_out.stat().st_size == 0:
            return {
                "ok": False,
                "app": "lightcraft",
                "command": cmd,
                "error": "lightcraft-cli did not produce a non-empty output file",
            }

        out_info = inspect_image(str(tmp_out))
        if (
            not out_info.get("valid")
            or out_info.get("width", 0) <= 0
            or out_info.get("height", 0) <= 0
        ):
            err_detail = out_info.get("error", "invalid image")
            return {
                "ok": False,
                "app": "lightcraft",
                "command": cmd,
                "error": f"Rendered output failed image verification: {err_detail}",
            }

        if sha256_file(src_path) != source_sha256:
            return {
                "ok": False,
                "app": "lightcraft",
                "error": "non_destructive_violation: source file hash changed during execution",
            }

        _atomic_promote(tmp_out, out_path, allow_overwrite=allow_overwrite)

    output_sha256 = sha256_file(out_path)
    return {
        "ok": True,
        "app": "lightcraft",
        "input_path": str(src_path),
        "output_path": str(out_path),
        "source_sha256": source_sha256,
        "output_sha256": output_sha256,
        "width": out_info["width"],
        "height": out_info["height"],
        "format": out_info["format"],
        "command": cmd,
        "elapsed_ms": elapsed_ms,
    }


def _soundcraft_probe_dict(
    binary: Path, target_path: Path, timeout_s: float = 30.0
) -> Dict[str, Any]:
    """Run `soundcraft-cli info <FILE>` and return parsed JSON metadata."""
    proc = subprocess.run(
        [str(binary), "info", str(target_path)],
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"soundcraft-cli info exited with code {proc.returncode}: {detail}")
    out = proc.stdout.strip()
    try:
        parsed = json.loads(out)
    except Exception as exc:
        raise RuntimeError(f"Failed to parse soundcraft-cli info JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("soundcraft-cli info did not return a JSON object")
    return parsed


def soundcraft_audio_basic(
    action: str,
    input_path: str,
    *,
    output_path: Optional[str] = None,
    sample_rate: Optional[int] = None,
    bit_depth: Optional[str] = None,
    normalize: bool = False,
    dither: Optional[bool] = None,
    allow_overwrite: bool = False,
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Probe or non-destructively convert/normalize an audio file via `soundcraft-cli`."""
    if action not in ("info", "convert"):
        return {
            "ok": False,
            "app": "soundcraft",
            "error": f"Unsupported action {action!r}; must be 'info' or 'convert'",
        }

    src_path = Path(input_path).expanduser()
    if not src_path.is_file():
        return {
            "ok": False,
            "app": "soundcraft",
            "action": action,
            "error": f"Input file does not exist: {src_path}",
        }

    binary = find_cli_binary("soundcraft")
    if binary is None:
        return {
            "ok": False,
            "app": "soundcraft",
            "action": action,
            "error": "soundcraft-cli binary not found on PATH or standard ArtCraft locations",
        }

    source_sha256 = sha256_file(src_path)

    if action == "info":
        try:
            info = _soundcraft_probe_dict(binary, src_path, timeout_s=timeout_s)
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "app": "soundcraft",
                "action": "info",
                "error": f"timeout: soundcraft-cli info exceeded {timeout_s}s",
            }
        except Exception as exc:
            return {"ok": False, "app": "soundcraft", "action": "info", "error": str(exc)}

        if sha256_file(src_path) != source_sha256:
            return {
                "ok": False,
                "app": "soundcraft",
                "action": "info",
                "error": "non_destructive_violation: source file hash changed during info probe",
            }

        return {
            "ok": True,
            "app": "soundcraft",
            "action": "info",
            "input_path": str(src_path),
            "source_sha256": source_sha256,
            "info": info,
        }

    # action == "convert"
    if not output_path or not str(output_path).strip():
        return {
            "ok": False,
            "app": "soundcraft",
            "action": "convert",
            "error": "output_path is required when action='convert'",
        }

    out_path = Path(output_path).expanduser()
    if _paths_refer_to_same_file(src_path, out_path):
        return {
            "ok": False,
            "app": "soundcraft",
            "action": "convert",
            "error": "non_destructive_guard: output_path must be distinct from input_path",
        }

    if os.path.lexists(out_path) and not allow_overwrite:
        return {
            "ok": False,
            "app": "soundcraft",
            "action": "convert",
            "error": (
                f"Output file already exists: {out_path} "
                "(set allow_overwrite=True to overwrite)"
            ),
        }

    if bit_depth is not None and str(bit_depth) not in ("16", "24", "32f"):
        return {
            "ok": False,
            "app": "soundcraft",
            "action": "convert",
            "error": f"Invalid bit_depth {bit_depth!r}; must be '16', '24', or '32f'",
        }

    if sample_rate is not None and int(sample_rate) <= 0:
        return {
            "ok": False,
            "app": "soundcraft",
            "action": "convert",
            "error": "sample_rate must be a positive integer",
        }

    try:
        input_info = _soundcraft_probe_dict(binary, src_path, timeout_s=timeout_s)
    except Exception as exc:
        return {
            "ok": False,
            "app": "soundcraft",
            "action": "convert",
            "error": f"Input audio probe failed: {exc}",
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_path.suffix or ".wav"

    with TemporaryDirectory(prefix=".artcraft-sc-", dir=out_path.parent) as tmp_dir:
        tmp_out = Path(tmp_dir) / f"converted{suffix}"
        cmd: List[str] = [str(binary), "convert", str(src_path), str(tmp_out)]
        if sample_rate is not None:
            cmd.extend(["--rate", str(int(sample_rate))])
        if bit_depth is not None:
            cmd.extend(["--bit-depth", str(bit_depth)])
        if normalize:
            cmd.append("--normalize")
        if dither is True:
            cmd.append("--dither")
        elif dither is False:
            cmd.append("--no-dither")

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
                "app": "soundcraft",
                "action": "convert",
                "command": cmd,
                "error": f"timeout: soundcraft-cli convert exceeded {timeout_s}s",
            }
        except Exception as exc:
            return {
                "ok": False,
                "app": "soundcraft",
                "action": "convert",
                "command": cmd,
                "error": f"execution_failed: {exc}",
            }

        if proc.returncode != 0:
            return {
                "ok": False,
                "app": "soundcraft",
                "action": "convert",
                "command": cmd,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "error": f"soundcraft-cli convert exited with code {proc.returncode}",
            }

        if not tmp_out.is_file() or tmp_out.stat().st_size == 0:
            return {
                "ok": False,
                "app": "soundcraft",
                "action": "convert",
                "command": cmd,
                "error": "soundcraft-cli convert did not produce a non-empty output file",
            }

        if sha256_file(src_path) != source_sha256:
            return {
                "ok": False,
                "app": "soundcraft",
                "action": "convert",
                "error": "non_destructive_violation: source file hash changed during conversion",
            }

        _atomic_promote(tmp_out, out_path, allow_overwrite=allow_overwrite)

    try:
        output_info = _soundcraft_probe_dict(binary, out_path, timeout_s=timeout_s)
    except Exception as exc:
        return {
            "ok": False,
            "app": "soundcraft",
            "action": "convert",
            "error": f"Converted output failed verification probe: {exc}",
        }

    output_sha256 = sha256_file(out_path)
    return {
        "ok": True,
        "app": "soundcraft",
        "action": "convert",
        "input_path": str(src_path),
        "output_path": str(out_path),
        "source_sha256": source_sha256,
        "output_sha256": output_sha256,
        "input_info": input_info,
        "output_info": output_info,
        "command": cmd,
    }


def _check_jsonl_run_output(stdout_text: str) -> Optional[str]:
    """Inspect `filmcraft-cli run -` JSONL output and return an error message if any failed."""
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("ok") is False:
            return str(obj.get("error") or f"Command {obj.get('id')} failed")
    return None


def filmcraft_video_basic(
    action: str,
    *,
    input_path: Optional[str] = None,
    project_path: Optional[str] = None,
    demo: bool = False,
    output_path: Optional[str] = None,
    seconds: float = 0.0,
    start_seconds: Optional[float] = None,
    end_seconds: Optional[float] = None,
    format: Optional[str] = None,
    preset: Optional[str] = None,
    scale: Optional[float] = None,
    quality: Optional[int] = None,
    no_audio: bool = False,
    allow_overwrite: bool = False,
    timeout_s: float = 180.0,
) -> Dict[str, Any]:
    """Probe media, extract frames, or export video/audio non-destructively via `filmcraft-cli`."""
    if action not in ("probe", "render_frame", "export"):
        return {
            "ok": False,
            "app": "filmcraft",
            "error": f"Unsupported action {action!r}; must be 'probe', 'render_frame', or 'export'",
        }

    binary = find_cli_binary("filmcraft")
    if binary is None:
        return {
            "ok": False,
            "app": "filmcraft",
            "action": action,
            "error": "filmcraft-cli binary not found on PATH or standard ArtCraft locations",
        }

    src_path: Optional[Path] = Path(input_path).expanduser() if input_path else None
    proj_path: Optional[Path] = Path(project_path).expanduser() if project_path else None
    source_sha256: Optional[str] = None

    if src_path is not None:
        if not src_path.is_file():
            return {
                "ok": False,
                "app": "filmcraft",
                "action": action,
                "error": f"Input file does not exist: {src_path}",
            }
        source_sha256 = sha256_file(src_path)

    if proj_path is not None:
        if not proj_path.is_file():
            return {
                "ok": False,
                "app": "filmcraft",
                "action": action,
                "error": f"Project file does not exist: {proj_path}",
            }
        if source_sha256 is None:
            source_sha256 = sha256_file(proj_path)

    if action == "probe":
        if src_path is None:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "probe",
                "error": "input_path is required when action='probe'",
            }
        cmd = [str(binary), "probe", str(src_path)]
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
                "app": "filmcraft",
                "action": "probe",
                "command": cmd,
                "error": f"timeout: filmcraft-cli probe exceeded {timeout_s}s",
            }
        except Exception as exc:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "probe",
                "command": cmd,
                "error": f"execution_failed: {exc}",
            }

        if proc.returncode != 0:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "probe",
                "command": cmd,
                "returncode": proc.returncode,
                "stderr": proc.stderr.strip(),
                "error": f"filmcraft-cli probe exited with code {proc.returncode}",
            }

        try:
            probe_data = json.loads(proc.stdout.strip())
        except Exception as exc:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "probe",
                "error": f"Failed to parse filmcraft-cli probe JSON: {exc}",
            }

        if sha256_file(src_path) != source_sha256:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "probe",
                "error": "non_destructive_violation: source file hash changed during probe",
            }

        return {
            "ok": True,
            "app": "filmcraft",
            "action": "probe",
            "input_path": str(src_path),
            "source_sha256": source_sha256,
            "probe": probe_data,
        }

    # Both render_frame and export require output_path and one source (input, project, or demo)
    if not output_path or not str(output_path).strip():
        return {
            "ok": False,
            "app": "filmcraft",
            "action": action,
            "error": f"output_path is required when action={action!r}",
        }

    if src_path is None and proj_path is None and not demo:
        return {
            "ok": False,
            "app": "filmcraft",
            "action": action,
            "error": "Provide one of input_path, project_path, or demo=True",
        }

    out_path = Path(output_path).expanduser()
    if src_path is not None and _paths_refer_to_same_file(src_path, out_path):
        return {
            "ok": False,
            "app": "filmcraft",
            "action": action,
            "error": "non_destructive_guard: output_path must be distinct from input_path",
        }
    if proj_path is not None and _paths_refer_to_same_file(proj_path, out_path):
        return {
            "ok": False,
            "app": "filmcraft",
            "action": action,
            "error": "non_destructive_guard: output_path must be distinct from project_path",
        }

    if os.path.lexists(out_path) and not allow_overwrite:
        return {
            "ok": False,
            "app": "filmcraft",
            "action": action,
            "error": (
                f"Output file already exists: {out_path} "
                "(set allow_overwrite=True to overwrite)"
            ),
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if action == "render_frame":
        with TemporaryDirectory(prefix=".artcraft-fc-frame-", dir=out_path.parent) as tmp_dir:
            tmp_out = Path(tmp_dir) / "frame.png"
            stdin_payload: Optional[str] = None

            if proj_path is not None or demo:
                cmd = [str(binary)]
                if proj_path is not None:
                    cmd.extend(["--project", str(proj_path)])
                else:
                    cmd.append("--demo")
                cmd.extend(["render", "--seconds", str(float(seconds)), "--out", str(tmp_out)])
                if scale is not None:
                    cmd.extend(["--scale", str(float(scale))])
            else:
                assert src_path is not None
                ticks = int(round(float(seconds) * FILMCRAFT_TICKS_PER_SECOND))
                export_frame_params: Dict[str, Any] = {
                    "path": str(tmp_out),
                    "format": "png",
                    "time": ticks,
                }
                lines = [
                    json.dumps({"id": "file.import", "params": {"paths": [str(src_path)]}}),
                    json.dumps({"id": "file.newSequenceFromClip", "params": {"items": [1]}}),
                    json.dumps({"id": "file.exportFrame", "params": export_frame_params}),
                ]
                stdin_payload = "\n".join(lines) + "\n"
                cmd = [str(binary), "run", "-"]

            try:
                proc = subprocess.run(
                    cmd,
                    input=stdin_payload,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return {
                    "ok": False,
                    "app": "filmcraft",
                    "action": "render_frame",
                    "command": cmd,
                    "error": f"timeout: filmcraft-cli render_frame exceeded {timeout_s}s",
                }
            except Exception as exc:
                return {
                    "ok": False,
                    "app": "filmcraft",
                    "action": "render_frame",
                    "command": cmd,
                    "error": f"execution_failed: {exc}",
                }

            if proc.returncode != 0:
                return {
                    "ok": False,
                    "app": "filmcraft",
                    "action": "render_frame",
                    "command": cmd,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                    "error": f"filmcraft-cli exited with code {proc.returncode}",
                }

            if stdin_payload is not None:
                jsonl_err = _check_jsonl_run_output(proc.stdout)
                if jsonl_err:
                    return {
                        "ok": False,
                        "app": "filmcraft",
                        "action": "render_frame",
                        "command": cmd,
                        "error": f"filmcraft-cli run error: {jsonl_err}",
                    }

                # Scale standalone clip frames since only --project/--demo accept --scale.
                if (
                    scale is not None
                    and float(scale) > 0
                    and float(scale) != 1.0
                    and tmp_out.is_file()
                ):
                    with Image.open(tmp_out) as im:
                        new_w = max(1, int(round(im.width * float(scale))))
                        new_h = max(1, int(round(im.height * float(scale))))
                        resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
                        resized.save(tmp_out, format="PNG")

            frame_info = inspect_image(str(tmp_out))
            if (
                not frame_info.get("valid")
                or frame_info.get("width", 0) <= 0
                or frame_info.get("height", 0) <= 0
            ):
                err_detail = frame_info.get("error", "invalid image")
                return {
                    "ok": False,
                    "app": "filmcraft",
                    "action": "render_frame",
                    "command": cmd,
                    "error": f"Rendered frame PNG failed verification: {err_detail}",
                }

            if src_path is not None and sha256_file(src_path) != source_sha256:
                return {
                    "ok": False,
                    "app": "filmcraft",
                    "action": "render_frame",
                    "error": (
                        "non_destructive_violation: source file hash changed during render_frame"
                    ),
                }
            if (
                proj_path is not None
                and src_path is None
                and sha256_file(proj_path) != source_sha256
            ):
                return {
                    "ok": False,
                    "app": "filmcraft",
                    "action": "render_frame",
                    "error": (
                        "non_destructive_violation: project file hash changed during render_frame"
                    ),
                }

            _atomic_promote(tmp_out, out_path, allow_overwrite=allow_overwrite)

        output_sha256 = sha256_file(out_path)
        return {
            "ok": True,
            "app": "filmcraft",
            "action": "render_frame",
            "input_path": str(src_path) if src_path else None,
            "project_path": str(proj_path) if proj_path else None,
            "demo": bool(demo),
            "output_path": str(out_path),
            "seconds": float(seconds),
            "source_sha256": source_sha256,
            "output_sha256": output_sha256,
            "width": frame_info["width"],
            "height": frame_info["height"],
            "format": frame_info["format"],
            "command": cmd,
        }

    # action == "export"
    suffix = out_path.suffix or ".mp4"
    with TemporaryDirectory(prefix=".artcraft-fc-exp-", dir=out_path.parent) as tmp_dir:
        tmp_out = Path(tmp_dir) / f"exported{suffix}"
        stdin_payload = None

        if proj_path is not None or demo:
            cmd = [str(binary)]
            if proj_path is not None:
                cmd.extend(["--project", str(proj_path)])
            else:
                cmd.append("--demo")
            cmd.extend(["export", str(tmp_out)])
            if preset:
                cmd.extend(["--preset", str(preset)])
            if format:
                cmd.extend(["--format", str(format)])
            if start_seconds is not None or end_seconds is not None:
                s_val = float(start_seconds) if start_seconds is not None else 0.0
                e_val = float(end_seconds) if end_seconds is not None else max(s_val, 1.0)
                cmd.extend(["--range", "custom", "--start", str(s_val), "--end", str(e_val)])
            if scale is not None:
                cmd.extend(["--scale", str(float(scale))])
            if quality is not None:
                cmd.extend(["--quality", str(int(quality))])
            if no_audio:
                cmd.append("--no-audio")
        else:
            assert src_path is not None
            export_params: Dict[str, Any] = {
                "path": str(tmp_out),
                "audio": not bool(no_audio),
                "includeAudio": not bool(no_audio),
            }
            if format:
                export_params["format"] = str(format)
            if preset:
                export_params["preset"] = str(preset)
            if start_seconds is not None or end_seconds is not None:
                export_params["range"] = "custom"
                if start_seconds is not None:
                    export_params["startSeconds"] = float(start_seconds)
                if end_seconds is not None:
                    export_params["endSeconds"] = float(end_seconds)
            if scale is not None:
                export_params["scale"] = float(scale)
            if quality is not None:
                export_params["quality"] = int(quality)

            lines = [
                json.dumps({"id": "file.import", "params": {"paths": [str(src_path)]}}),
                json.dumps({"id": "file.newSequenceFromClip", "params": {"items": [1]}}),
                json.dumps({"id": "file.exportMedia", "params": export_params}),
            ]
            stdin_payload = "\n".join(lines) + "\n"
            cmd = [str(binary), "run", "-"]

        try:
            proc = subprocess.run(
                cmd,
                input=stdin_payload,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "export",
                "command": cmd,
                "error": f"timeout: filmcraft-cli export exceeded {timeout_s}s",
            }
        except Exception as exc:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "export",
                "command": cmd,
                "error": f"execution_failed: {exc}",
            }

        if proc.returncode != 0:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "export",
                "command": cmd,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
                "error": f"filmcraft-cli export exited with code {proc.returncode}",
            }

        if stdin_payload is not None:
            jsonl_err = _check_jsonl_run_output(proc.stdout)
            if jsonl_err:
                return {
                    "ok": False,
                    "app": "filmcraft",
                    "action": "export",
                    "command": cmd,
                    "error": f"filmcraft-cli run error: {jsonl_err}",
                }

        if not tmp_out.is_file() or tmp_out.stat().st_size == 0:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "export",
                "command": cmd,
                "error": "filmcraft-cli export did not produce a non-empty output file",
            }

        if src_path is not None and sha256_file(src_path) != source_sha256:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "export",
                "error": "non_destructive_violation: source file hash changed during export",
            }
        if proj_path is not None and src_path is None and sha256_file(proj_path) != source_sha256:
            return {
                "ok": False,
                "app": "filmcraft",
                "action": "export",
                "error": "non_destructive_violation: project file hash changed during export",
            }

        _atomic_promote(tmp_out, out_path, allow_overwrite=allow_overwrite)

    output_sha256 = sha256_file(out_path)
    size_bytes = out_path.stat().st_size
    return {
        "ok": True,
        "app": "filmcraft",
        "action": "export",
        "input_path": str(src_path) if src_path else None,
        "project_path": str(proj_path) if proj_path else None,
        "demo": bool(demo),
        "output_path": str(out_path),
        "size_bytes": size_bytes,
        "source_sha256": source_sha256,
        "output_sha256": output_sha256,
        "command": cmd,
    }
