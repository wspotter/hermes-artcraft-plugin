"""Discover installed ArtCraft CLI binaries and report their versions."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTCRAFT_APPS: Dict[str, tuple[str, ...]] = {
    "photocraft": ("photocraft-cli", "photocraft"),
    "lightcraft": ("lightcraft-cli", "lightcraft"),
    "filmcraft": ("filmcraft-cli", "filmcraft"),
    "soundcraft": ("soundcraft-cli", "soundcraft"),
}

_EXTRA_SEARCH_DIRS: tuple[Path, ...] = (
    Path.home() / ".local" / "bin",
    Path.home() / "bin",
    Path.home() / ".local" / "share" / "ArtCraft" / "bin",
    Path("/usr/local/bin"),
)


@dataclass(frozen=True)
class BinaryInfo:
    """Metadata for a discovered ArtCraft CLI binary."""

    app: str
    binary_name: str
    path: Optional[str]
    version: Optional[str]
    available: bool

    def to_dict(self) -> dict:
        return {
            "app": self.app,
            "binary_name": self.binary_name,
            "path": self.path,
            "version": self.version,
            "available": self.available,
        }


def _candidate_dirs(extra_dirs: Optional[List[Path]] = None) -> List[Path]:
    dirs: List[Path] = []
    env_dir = os.environ.get("ARTCRAFT_BIN_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).expanduser())
    if extra_dirs:
        dirs.extend(extra_dirs)

    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    if hermes_home:
        dirs.append(Path(hermes_home).expanduser() / "bin")

    hermes_profile = os.environ.get("HERMES_PROFILE", "").strip()
    if hermes_profile:
        dirs.append(Path.home() / ".hermes" / "profiles" / hermes_profile / "bin")

    profiles_root = Path.home() / ".hermes" / "profiles"
    if profiles_root.is_dir():
        for profile_bin in sorted(profiles_root.glob("*/bin")):
            if profile_bin not in dirs:
                dirs.append(profile_bin)
    dirs.append(Path.home() / ".hermes" / "bin")

    dirs.extend(_EXTRA_SEARCH_DIRS)
    return dirs


def find_cli_binary(
    app: str,
    extra_dirs: Optional[List[Path]] = None,
) -> Optional[Path]:
    """Locate the CLI executable for an ArtCraft app, preferring *-cli over GUI binaries."""
    names = ARTCRAFT_APPS.get(app.lower())
    if not names:
        raise ValueError(f"Unknown ArtCraft app: {app!r}")

    name = names[0]
    for directory in _candidate_dirs(extra_dirs):
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    found = shutil.which(name)
    if found:
        return Path(found)
    return None


def probe_version(binary_path: Path, timeout_s: float = 5.0) -> Optional[str]:
    """Query `--version` from a CLI binary without raising on failure."""
    try:
        proc = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return out.splitlines()[0] if out else None
    except Exception:
        return None


def discover_all(extra_dirs: Optional[List[Path]] = None) -> Dict[str, BinaryInfo]:
    """Discover all known ArtCraft CLIs and return a mapping keyed by app name."""
    results: Dict[str, BinaryInfo] = {}
    for app, names in ARTCRAFT_APPS.items():
        path = find_cli_binary(app, extra_dirs=extra_dirs)
        if path is None:
            results[app] = BinaryInfo(
                app=app,
                binary_name=names[0],
                path=None,
                version=None,
                available=False,
            )
        else:
            results[app] = BinaryInfo(
                app=app,
                binary_name=path.name,
                path=str(path),
                version=probe_version(path),
                available=True,
            )
    return results


_STANDALONE_PILLOW_TOOLS: tuple[str, ...] = (
    "artcraft_inspect",
    "artcraft_prepare_inspection",
    "artcraft_prepare_print",
    "artcraft_verify_edit",
    "artcraft_checkpoint",
    "artcraft_build_review",
    "artcraft_job",
)

_RESTORE_RECIPES: tuple[str, ...] = (
    "faded_tones",
    "color_cast",
    "dust_and_scratches",
    "noise_and_grain",
    "sharpening",
    "enlargement",
)

_CLI_TOOL_MAP: Dict[str, tuple[str, ...]] = {
    "photocraft": ("photocraft_run", "photocraft_spot_heal", "artcraft_restore_step"),
    "lightcraft": ("lightcraft_run", "artcraft_develop"),
    "filmcraft": ("artcraft_video_basic",),
    "soundcraft": ("artcraft_audio_basic",),
}


def _has_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def summarize_capabilities(
    discovered: Dict[str, BinaryInfo],
    *,
    pillow_available: Optional[bool] = None,
) -> Dict[str, Any]:
    """Summarize which tools run standalone with Pillow vs require ArtCraft CLIs."""
    has_pil = _has_pillow() if pillow_available is None else pillow_available
    available_tools: List[str] = ["artcraft_status"]
    unavailable_tools: Dict[str, str] = {}

    standalone_tools = ["artcraft_status"]
    for tool_name in _STANDALONE_PILLOW_TOOLS:
        standalone_tools.append(tool_name)
        if has_pil:
            available_tools.append(tool_name)
        else:
            unavailable_tools[tool_name] = "Requires Pillow (PIL)"

    photocraft_ok = bool(discovered.get("photocraft") and discovered["photocraft"].available)
    restore_ok = has_pil and photocraft_ok

    cli_tools: Dict[str, Dict[str, Any]] = {}
    for app, tool_names in _CLI_TOOL_MAP.items():
        info = discovered.get(app)
        app_ok = bool(info and info.available)
        cli_tools[app] = {
            "available": app_ok,
            "tools": list(tool_names),
        }
        binary_label = info.binary_name if info else f"{app}-cli"
        for tool_name in tool_names:
            if tool_name == "artcraft_restore_step":
                if restore_ok:
                    available_tools.append(tool_name)
                elif not app_ok:
                    unavailable_tools[tool_name] = f"Requires {binary_label} (not found)"
                else:
                    unavailable_tools[tool_name] = "Requires Pillow (PIL)"
            elif app_ok:
                available_tools.append(tool_name)
            else:
                unavailable_tools[tool_name] = f"Requires {binary_label} (not found)"

    return {
        "pillow_available": has_pil,
        "standalone_tools": standalone_tools,
        "partial_tools": {
            "artcraft_restore_step": {
                "available": restore_ok,
                "standalone_recipes": [],
                "cli_recipes": {
                    recipe: {
                        "requires_app": "photocraft",
                        "available": restore_ok,
                    }
                    for recipe in _RESTORE_RECIPES
                },
            }
        },
        "cli_tools": cli_tools,
        "available_tools": sorted(available_tools),
        "unavailable_tools": unavailable_tools,
    }


def status_payload(extra_dirs: Optional[List[Path]] = None) -> Dict[str, Any]:
    """Return full ArtCraft discovery and tool capability payload."""
    discovered = discover_all(extra_dirs=extra_dirs)
    return {
        "ok": True,
        "apps": {name: info.to_dict() for name, info in discovered.items()},
        "capabilities": summarize_capabilities(discovered),
    }
