"""Discover installed ArtCraft CLI binaries and report their versions."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

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

    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)

    for directory in _candidate_dirs(extra_dirs):
        if not directory.is_dir():
            continue
        for name in names:
            candidate = directory / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
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
