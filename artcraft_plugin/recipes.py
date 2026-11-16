"""Portable ArtCraft recipe validation, scaffolding, trading, and replay engine."""

from __future__ import annotations

import json
import math
import os
import posixpath
import re
import shutil
import stat
import tempfile
import zipfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .jobs import _ensure_within_dir, _validate_safe_id
from .runner import _paths_refer_to_same_file, atomic_replace_file
from .verify import sha256_file

SUPPORTED_APPS = ("photocraft", "lightcraft", "soundcraft", "filmcraft")

APP_MEDIA_TYPES: Dict[str, str] = {
    "photocraft": "photo",
    "lightcraft": "photo",
    "soundcraft": "audio",
    "filmcraft": "video",
}

APP_DEFAULT_SUFFIX: Dict[str, str] = {
    "photocraft": ".png",
    "lightcraft": ".jpg",
    "soundcraft": ".wav",
    "filmcraft": ".mp4",
}

ALLOWED_RECIPE_TOOL_NAMES = frozenset({
    "artcraft_inspect",
    "artcraft_prepare_inspection",
    "artcraft_develop",
    "artcraft_restore_step",
    "photocraft_spot_heal",
    "artcraft_prepare_print",
    "artcraft_audio_basic",
    "artcraft_video_basic",
    "artcraft_verify_edit",
    "artcraft_build_review",
})

READ_ONLY_TOOLS = frozenset({
    "artcraft_inspect",
    "artcraft_prepare_inspection",
    "artcraft_verify_edit",
    "artcraft_build_review",
})

PATH_ARG_KEYS = frozenset({
    "input_path",
    "output_path",
    "source_path",
    "path",
    "working_dir",
    "checkpoint_dir",
    "last_checkpoint_path",
    "preserve_master_path",
    "project_path",
})

WRITE_PATH_KEYS = frozenset({
    "output_path",
    "working_dir",
    "checkpoint_dir",
    "preserve_master_path",
})

ALLOWED_PARAM_TYPES = frozenset({"string", "number", "integer", "boolean", "array", "object"})

ALLOWED_BUNDLE_TOP_FILES = frozenset({"SKILL.md", "recipe.json", "checksums.json"})
ALLOWED_ASSET_SUBDIRS = frozenset({"assets", "presets"})
ALLOWED_ASSET_EXTENSIONS = frozenset({
    ".md",
    ".json",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".icc",
    ".cube",
    ".xmp",
})

MAX_MANIFEST_BYTES = 512 * 1024
MAX_RECIPE_FILE_BYTES = 1024 * 1024
MAX_RECIPE_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_RECIPE_EXTRACTED_BYTES = 4 * 1024 * 1024
MAX_RECIPE_STEPS = 32

# Shared portability hygiene patterns (reused by tests/test_skill_standards.py).
BANNED_MARKETING = re.compile(
    r"\b(powerful|comprehensive|seamless|advanced|revolutionary|cutting-edge|state-of-the-art)\b",
    re.IGNORECASE,
)
MACHINE_LOCAL_PATH = re.compile(
    r"(/(?:Users|home|workspace)/[A-Za-z0-9._-]+|[A-Za-z]:\\(?:Users|home)\\[A-Za-z0-9._-]+)"
)
RFC1918_IP = re.compile(
    r"\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b"
)
SHELL_FENCE_OPEN = re.compile(r"^```(?:bash|sh|zsh|shell)\s*$")
CONTINUATION_THEN_COMMENT = re.compile(r"\\\s*$")
RAW_SHELL_TOOLS = re.compile(r"\b(cat|head|tail|grep|ls|sed)\b")
HARDCODED_TMP = re.compile(r"(?<![A-Za-z0-9_.-])/tmp(?:/[A-Za-z0-9._-]+)*")

REQUIRED_SECTIONS = [
    "## When to Use",
    "## Prerequisites",
    "## How to Run",
    "## Procedure",
    "## Pitfalls",
    "## Verification",
]

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_PARAM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9]{1,10}$")


def bundled_skills_dir() -> Path:
    """Return the bundled `skills/` directory shipped with this plugin."""
    return Path(__file__).resolve().parent.parent / "skills"


def default_user_skills_dir() -> Path:
    """Return the default writable user recipe/skills directory."""
    override = os.environ.get("ARTCRAFT_RECIPES_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    if hermes_home:
        return Path(hermes_home).expanduser() / "skills"
    return Path.home() / ".hermes" / "skills"


def _strip_yaml_comment(line: str) -> str:
    """Strip unquoted `# ...` comments from a YAML line."""
    quote: Optional[str] = None
    escaped = False
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if quote == '"' and ch == "\\":
            escaped = True
            continue
        if ch in ("'", '"'):
            if quote is None:
                quote = ch
            elif quote == ch:
                quote = None
        elif ch == "#" and quote is None and (idx == 0 or line[idx - 1].isspace()):
            return line[:idx].rstrip()
    return line.rstrip()


def _parse_yaml_scalar(raw: str) -> Any:
    """Parse a simple YAML scalar or inline `[a, b]` list without PyYAML."""
    val = raw.strip()
    if not val or val in ("null", "~"):
        return None
    if val == "true":
        return True
    if val == "false":
        return False
    if val == "{}":
        return {}
    if val == "[]":
        return []
    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
        inner = val[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    if len(val) >= 2 and val[0] == "'" and val[-1] == "'":
        return val[1:-1].replace("''", "'")
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(part) for part in _split_inline_csv(inner)]
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    if re.fullmatch(r"-?\d+\.\d+", val):
        return float(val)
    return val


def _split_inline_csv(text: str) -> List[str]:
    """Split comma-separated items while respecting single/double quotes."""
    items: List[str] = []
    cur: List[str] = []
    quote: Optional[str] = None
    for ch in text:
        if ch in ("'", '"'):
            if quote is None:
                quote = ch
            elif quote == ch:
                quote = None
            cur.append(ch)
        elif ch == "," and quote is None:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur or text.endswith(","):
        items.append("".join(cur).strip())
    return items


def _parse_yaml_block(lines: Sequence[Tuple[int, str]], start: int, indent: int) -> Tuple[Any, int]:
    """Parse an indented YAML dict or list block recursively."""
    if start >= len(lines):
        return {}, start

    if lines[start][1].startswith("- ") or lines[start][1] == "-":
        items: List[Any] = []
        idx = start
        while idx < len(lines):
            ln_indent, content = lines[idx]
            if ln_indent < indent:
                break
            if ln_indent > indent:
                raise ValueError(f"Unexpected indentation in YAML list at: {content!r}")
            if not (content.startswith("- ") or content == "-"):
                break
            rest = content[1:].strip()
            idx += 1
            if rest:
                items.append(_parse_yaml_scalar(rest))
            elif idx < len(lines) and lines[idx][0] > ln_indent:
                sub, idx = _parse_yaml_block(lines, idx, lines[idx][0])
                items.append(sub)
            else:
                items.append(None)
        return items, idx

    mapping: Dict[str, Any] = {}
    idx = start
    while idx < len(lines):
        ln_indent, content = lines[idx]
        if ln_indent < indent:
            break
        if ln_indent > indent:
            raise ValueError(f"Unexpected indentation in YAML mapping at: {content!r}")
        if content.startswith("- ") or ":" not in content:
            raise ValueError(f"Expected 'key: value' in frontmatter line: {content!r}")
        key, _, rest = content.partition(":")
        key = key.strip()
        rest = rest.strip()
        idx += 1
        if rest:
            mapping[key] = _parse_yaml_scalar(rest)
        elif idx < len(lines) and lines[idx][0] > ln_indent:
            sub, idx = _parse_yaml_block(lines, idx, lines[idx][0])
            mapping[key] = sub
        elif idx < len(lines) and lines[idx][0] == ln_indent and lines[idx][1].startswith("- "):
            sub, idx = _parse_yaml_block(lines, idx, ln_indent)
            mapping[key] = sub
        else:
            mapping[key] = None
    return mapping, idx


def parse_skill_frontmatter(text: str) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
    """Parse YAML frontmatter from SKILL.md without external dependencies."""
    if not text.startswith("---"):
        return None, text, "Missing YAML frontmatter opening '---'"
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text, "Unclosed YAML frontmatter delimiter '---'"
    raw_lines: List[Tuple[int, str]] = []
    for raw in parts[1].splitlines():
        cleaned = _strip_yaml_comment(raw)
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        raw_lines.append((indent, cleaned.strip()))
    if not raw_lines:
        return {}, parts[2], None
    try:
        parsed, _ = _parse_yaml_block(raw_lines, 0, raw_lines[0][0])
    except ValueError as exc:
        return None, parts[2], str(exc)
    if not isinstance(parsed, dict):
        return None, parts[2], "Frontmatter root must be a mapping"
    return parsed, parts[2], None


def check_portability_text(text: str, label: str = "content") -> List[str]:
    """Check text for machine-local paths, RFC1918 IPs, and hardcoded `/tmp` paths."""
    errors: List[str] = []
    m_local = MACHINE_LOCAL_PATH.search(text)
    if m_local:
        errors.append(f"{label} contains machine-local path: {m_local.group(1)}")
    m_ip = RFC1918_IP.search(text)
    if m_ip:
        errors.append(f"{label} contains private RFC1918 IP: {m_ip.group(0)}")
    m_tmp = HARDCODED_TMP.search(text)
    if m_tmp:
        errors.append(f"{label} contains hardcoded /tmp path: {m_tmp.group(0)}")
    return errors


def _scan_json_strings(obj: Any) -> Iterable[Tuple[str, str]]:
    """Yield `(path, value)` pairs for every string anywhere inside a JSON structure."""
    if isinstance(obj, str):
        yield ("", obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            for sub_p, s in _scan_json_strings(v):
                yield (f"{k}.{sub_p}" if sub_p else str(k), s)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            for sub_p, s in _scan_json_strings(v):
                yield (f"[{i}].{sub_p}" if sub_p else f"[{i}]", s)


def _validate_skill_md(
    text: str, expected_dir_name: Optional[str]
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Validate SKILL.md frontmatter, structure, and portability hygiene."""
    errors: List[str] = []
    fm, _body, fm_err = parse_skill_frontmatter(text)
    if fm_err or fm is None:
        errors.append(f"SKILL.md frontmatter invalid: {fm_err}")
        return None, errors

    name = fm.get("name")
    if not isinstance(name, str) or not name.startswith("recipe-"):
        errors.append(f"SKILL.md frontmatter 'name' must start with 'recipe-', got {name!r}")
    else:
        try:
            _validate_safe_id(name, "recipe name")
        except ValueError as exc:
            errors.append(str(exc))
        if (
            expected_dir_name
            and expected_dir_name.startswith("recipe-")
            and name != expected_dir_name
        ):
            errors.append(
                f"SKILL.md 'name' ({name!r}) must match directory name ({expected_dir_name!r})"
            )

    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        errors.append("SKILL.md missing non-empty 'description'")
    else:
        if "\n" in desc:
            errors.append("SKILL.md 'description' must be single-line")
        if len(desc) > 60:
            errors.append(f"SKILL.md 'description' exceeds 60 chars ({len(desc)})")
        if not desc.endswith("."):
            errors.append("SKILL.md 'description' must end with a period '.'")
        bm = BANNED_MARKETING.search(desc)
        if bm:
            errors.append(f"SKILL.md 'description' contains marketing word {bm.group(1)!r}")

    for field in ("version", "author", "license"):
        val = fm.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"SKILL.md missing non-empty '{field}'")

    platforms = fm.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        errors.append("SKILL.md missing non-empty 'platforms' list")

    meta = fm.get("metadata")
    hermes_meta = meta.get("hermes") if isinstance(meta, dict) else None
    if not isinstance(hermes_meta, dict) or hermes_meta.get("category") != "creative":
        errors.append("SKILL.md metadata.hermes.category must equal 'creative'")
    else:
        if not isinstance(hermes_meta.get("tags"), list) or not hermes_meta.get("tags"):
            errors.append("SKILL.md metadata.hermes.tags must be a non-empty list")
        if not isinstance(hermes_meta.get("related_skills"), list):
            errors.append("SKILL.md metadata.hermes.related_skills must be a list")

    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"SKILL.md missing required section {section!r}")

    errors.extend(check_portability_text(text, label="SKILL.md"))
    raw_shell = RAW_SHELL_TOOLS.search(text)
    if raw_shell:
        errors.append(f"SKILL.md contains disallowed raw shell command {raw_shell.group(1)!r}")

    return fm, errors


def _validate_template_path_expr(step_id: str, key: str, expr: Any) -> List[str]:
    """Validate path argument templates inside `recipe.json` steps against traversal."""
    errors: List[str] = []
    if expr is None:
        return errors
    if not isinstance(expr, str) or not expr.strip():
        return [f"Step '{step_id}' arg '{key}' must be a non-empty string path template"]
    if "\x00" in expr or "\\" in expr:
        return [f"Step '{step_id}' arg '{key}' contains forbidden backslash or NUL byte"]
    if key in WRITE_PATH_KEYS and "{input}" in expr:
        errors.append(f"Step '{step_id}' write arg '{key}' must not target {{input}}")

    if expr in ("{input}", "{output}", "{work_dir}"):
        return errors

    prefix = "{work_dir}/"
    if not expr.startswith(prefix):
        errors.append(
            f"Step '{step_id}' arg '{key}' must be '{{input}}', '{{output}}', '{{work_dir}}', "
            f"or '{{work_dir}}/<subpath>', got {expr!r}"
        )
        return errors

    rel = expr[len(prefix) :]
    if not rel or rel.startswith("/"):
        errors.append(f"Step '{step_id}' arg '{key}' has empty or rooted subpath: {expr!r}")
        return errors
    if any(part in ("..", "") for part in rel.split("/")):
        errors.append(f"Step '{step_id}' arg '{key}' escapes {{work_dir}}: {expr!r}")
        return errors
    norm = posixpath.normpath(rel)
    if norm.startswith("..") or norm.startswith("/"):
        errors.append(f"Step '{step_id}' arg '{key}' normalizes outside {{work_dir}}: {expr!r}")
    return errors


def _validate_manifest(
    manifest: Any,
    *,
    expected_name: Optional[str],
) -> List[str]:
    """Validate an executable `recipe.json` manifest (schema v1.0)."""
    errors: List[str] = []
    if not isinstance(manifest, dict):
        return ["recipe.json root must be a JSON object"]

    if manifest.get("schema_version") != "1.0":
        errors.append(f"Unsupported recipe.json schema_version: {manifest.get('schema_version')!r}")

    name = manifest.get("name")
    if not isinstance(name, str) or not name.startswith("recipe-"):
        errors.append(f"recipe.json 'name' must start with 'recipe-', got {name!r}")
    else:
        try:
            _validate_safe_id(name, "recipe.json name")
        except ValueError as exc:
            errors.append(str(exc))
        if expected_name and name != expected_name:
            errors.append(f"recipe.json 'name' ({name!r}) must match {expected_name!r}")

    for req_str in ("title", "description", "version", "author", "license"):
        val = manifest.get(req_str)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"recipe.json missing non-empty '{req_str}'")

    app = manifest.get("app")
    if app not in SUPPORTED_APPS:
        errors.append(f"recipe.json 'app' must be one of {list(SUPPORTED_APPS)}, got {app!r}")

    media_type = manifest.get("media_type")
    if media_type not in ("photo", "audio", "video"):
        errors.append(
            f"recipe.json 'media_type' must be 'photo', 'audio', or 'video', got {media_type!r}"
        )

    suffix = manifest.get("default_output_suffix")
    if not isinstance(suffix, str) or not _SUFFIX_RE.fullmatch(suffix):
        errors.append(f"Invalid recipe.json 'default_output_suffix': {suffix!r}")

    params = manifest.get("parameters", {})
    if not isinstance(params, dict):
        errors.append("recipe.json 'parameters' must be an object mapping parameter names")
        param_names: set[str] = set()
    else:
        param_names = set()
        for p_name, p_spec in params.items():
            if not isinstance(p_name, str) or not _PARAM_NAME_RE.fullmatch(p_name):
                errors.append(f"Invalid parameter identifier in recipe.json: {p_name!r}")
                continue
            if not isinstance(p_spec, dict):
                errors.append(f"Parameter spec '{p_name}' must be an object")
                continue
            p_type = p_spec.get("type")
            if p_type not in ALLOWED_PARAM_TYPES:
                errors.append(f"Parameter '{p_name}' has invalid type {p_type!r}")
            param_names.add(p_name)

    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("recipe.json 'steps' must be a non-empty array")
        return errors
    if len(steps) > MAX_RECIPE_STEPS:
        errors.append(f"recipe.json 'steps' exceeds max {MAX_RECIPE_STEPS}")

    seen_ids: set[str] = set()
    writes_final_output = False
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"Step index {idx} must be an object")
            continue
        step_id = step.get("id")
        if not isinstance(step_id, str):
            errors.append(f"Step index {idx} missing string 'id'")
            continue
        try:
            _validate_safe_id(step_id, f"step[{idx}].id")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if step_id in seen_ids:
            errors.append(f"Duplicate recipe step id {step_id!r}")
        seen_ids.add(step_id)

        tool_name = step.get("tool")
        if not isinstance(tool_name, str) or tool_name not in ALLOWED_RECIPE_TOOL_NAMES:
            errors.append(
                f"Disallowed recipe step tool {tool_name!r} in step {step_id!r}. "
                f"Allowed: {sorted(ALLOWED_RECIPE_TOOL_NAMES)}"
            )
            continue

        step_args = step.get("args")
        if not isinstance(step_args, dict):
            errors.append(f"Step '{step_id}' 'args' must be an object")
            continue

        if step_args.get("output_path") == "{output}":
            writes_final_output = True

        for key in PATH_ARG_KEYS:
            if key in step_args:
                errors.extend(_validate_template_path_expr(step_id, key, step_args[key]))

        for key_path, s_val in _scan_json_strings(step_args):
            errors.extend(
                check_portability_text(s_val, label=f"recipe.json step '{step_id}' ({key_path})")
            )
            for match in _PLACEHOLDER_RE.finditer(s_val):
                token = match.group(1)
                if token in ("input", "output", "work_dir"):
                    continue
                if token.startswith("params."):
                    pname = token[len("params.") :]
                    if pname not in param_names:
                        errors.append(
                            f"Step '{step_id}' references undeclared parameter '{pname}'"
                        )
                else:
                    errors.append(
                        f"Step '{step_id}' contains unknown placeholder '{{{token}}}'"
                    )

    if not writes_final_output:
        errors.append("recipe.json must have at least one step targeting output_path='{output}'")

    for key_path, s_val in _scan_json_strings(manifest):
        if key_path.startswith("steps"):
            continue
        errors.extend(check_portability_text(s_val, label=f"recipe.json ({key_path})"))

    return errors


def _iter_search_roots(skills_dir: Optional[Union[str, Path]] = None) -> List[Tuple[str, Path]]:
    """Return ordered `(source_label, directory)` search roots, user dir first."""
    roots: List[Tuple[str, Path]] = []
    if skills_dir is not None:
        roots.append(("custom", Path(skills_dir).expanduser()))
    else:
        roots.append(("user", default_user_skills_dir()))
    b_dir = bundled_skills_dir()
    if not roots or roots[0][1].resolve() != b_dir.resolve():
        roots.append(("bundled", b_dir))
    return roots


def _resolve_recipe_dir(
    recipe: Union[str, Path],
    skills_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve a recipe slug, `recipe-*` name, or directory path to a recipe folder."""
    if isinstance(recipe, Path):
        return recipe.expanduser()
    text = str(recipe).strip()
    if not text:
        raise ValueError("Recipe identifier or path cannot be empty")

    looks_like_path = os.sep in text or "/" in text or text.startswith(".")
    if looks_like_path or Path(text).expanduser().is_dir():
        return Path(text).expanduser()

    candidates = [text]
    if not text.startswith("recipe-"):
        candidates.append(f"recipe-{text}")
    for cand in candidates:
        _validate_safe_id(cand, "recipe")

    for _source, root in _iter_search_roots(skills_dir):
        if not root.is_dir():
            continue
        for cand in candidates:
            target = root / cand
            _ensure_within_dir(target, root, "recipe directory")
            if target.is_dir():
                return target

    raise FileNotFoundError(f"Recipe not found: {recipe!r}")


def validate_recipe(
    recipe: Union[str, Path],
    *,
    skills_dir: Optional[Union[str, Path]] = None,
    require_manifest: bool = True,
) -> Dict[str, Any]:
    """Validate a recipe directory (`SKILL.md` + optional/required `recipe.json`)."""
    try:
        rdir = _resolve_recipe_dir(recipe, skills_dir=skills_dir)
    except Exception as exc:
        return {"ok": False, "recipe": str(recipe), "errors": [str(exc)], "warnings": []}

    if not rdir.is_dir():
        return {
            "ok": False,
            "recipe": rdir.name,
            "recipe_dir": str(rdir),
            "errors": [f"Recipe directory does not exist: {rdir}"],
            "warnings": [],
        }

    skill_md_path = rdir / "SKILL.md"
    manifest_path = rdir / "recipe.json"
    has_skill_md = skill_md_path.is_file()
    has_manifest = manifest_path.is_file()
    errors: List[str] = []
    warnings: List[str] = []
    frontmatter: Optional[Dict[str, Any]] = None
    manifest: Optional[Dict[str, Any]] = None

    if not has_skill_md:
        errors.append("Missing required SKILL.md")
    else:
        if skill_md_path.stat().st_size > MAX_RECIPE_FILE_BYTES:
            errors.append("SKILL.md exceeds maximum allowed size")
        else:
            fm, md_errors = _validate_skill_md(
                skill_md_path.read_text(encoding="utf-8"), rdir.name
            )
            frontmatter = fm
            errors.extend(md_errors)

    if not has_manifest:
        if require_manifest:
            errors.append("Missing required executable recipe.json manifest")
        else:
            warnings.append("No recipe.json manifest present (documentation-only skill)")
    else:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            errors.append("recipe.json exceeds maximum allowed size")
        else:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"Failed to parse recipe.json: {exc}")
            else:
                expected_name = (
                    frontmatter.get("name")
                    if isinstance(frontmatter, dict) and isinstance(frontmatter.get("name"), str)
                    else rdir.name
                )
                errors.extend(_validate_manifest(manifest, expected_name=expected_name))

    return {
        "ok": len(errors) == 0,
        "recipe": rdir.name,
        "recipe_dir": str(rdir),
        "has_skill_md": has_skill_md,
        "has_manifest": has_manifest,
        "app": manifest.get("app") if isinstance(manifest, dict) else None,
        "media_type": manifest.get("media_type") if isinstance(manifest, dict) else None,
        "step_count": len(manifest.get("steps", [])) if isinstance(manifest, dict) else 0,
        "errors": errors,
        "warnings": warnings,
        "manifest": manifest,
    }


def list_recipes(skills_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """List installed user and bundled `recipe-*` skills with manifest metadata."""
    by_name: Dict[str, Dict[str, Any]] = {}
    for source_label, root in _iter_search_roots(skills_dir):
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not child.name.startswith("recipe-"):
                continue
            if child.name in by_name:
                continue
            skill_md = child / "SKILL.md"
            manifest_file = child / "recipe.json"
            if not skill_md.is_file() and not manifest_file.is_file():
                continue

            entry: Dict[str, Any] = {
                "name": child.name,
                "source": source_label,
                "path": str(child),
                "has_skill_md": skill_md.is_file(),
                "has_manifest": manifest_file.is_file(),
                "description": None,
                "app": None,
                "media_type": None,
                "step_count": 0,
                "parameters": {},
            }
            if skill_md.is_file():
                fm, _, _ = parse_skill_frontmatter(skill_md.read_text(encoding="utf-8"))
                if isinstance(fm, dict):
                    entry["description"] = fm.get("description")
            if manifest_file.is_file():
                try:
                    mf = json.loads(manifest_file.read_text(encoding="utf-8"))
                    if isinstance(mf, dict):
                        entry["app"] = mf.get("app")
                        entry["media_type"] = mf.get("media_type")
                        entry["step_count"] = len(mf.get("steps", []))
                        entry["parameters"] = mf.get("parameters", {})
                        entry["version"] = mf.get("version")
                        entry["author"] = mf.get("author")
                except Exception as exc:
                    entry["manifest_error"] = str(exc)
            by_name[child.name] = entry

    items = [by_name[k] for k in sorted(by_name.keys())]
    return {
        "ok": True,
        "count": len(items),
        "runnable_count": sum(1 for item in items if item["has_manifest"]),
        "recipes": items,
    }


def _starter_template(
    name: str,
    title: str,
    app: str,
    author: str,
    description: str,
) -> Tuple[str, Dict[str, Any]]:
    """Generate a valid starter SKILL.md and recipe.json pair for `init_recipe`."""
    media_type = APP_MEDIA_TYPES[app]
    suffix = APP_DEFAULT_SUFFIX[app]
    cli_name = f"{app}-cli"

    if app == "photocraft":
        related = "[photo-restoration, photo-inspection, recipe-maker]"
        params = {
            "in_black": {"type": "integer", "default": 10},
            "in_white": {"type": "integer", "default": 244},
            "gamma": {"type": "number", "default": 1.05},
        }
        steps = [
            {
                "id": "inspect",
                "tool": "artcraft_prepare_inspection",
                "args": {"path": "{input}", "working_dir": "{work_dir}/inspect"},
            },
            {
                "id": "restore",
                "tool": "artcraft_restore_step",
                "args": {
                    "input_path": "{input}",
                    "output_path": "{output}",
                    "recipe": "faded_tones",
                    "parameters": {
                        "inBlack": "{params.in_black}",
                        "inWhite": "{params.in_white}",
                        "gamma": "{params.gamma}",
                    },
                    "checkpoint_dir": "{work_dir}/checkpoints",
                    "step_name": "01_restore",
                },
            },
            {
                "id": "review",
                "tool": "artcraft_build_review",
                "args": {
                    "source_path": "{input}",
                    "output_path": "{output}",
                    "working_dir": "{work_dir}/review",
                },
            },
        ]
    elif app == "lightcraft":
        related = "[lightcraft-basics, photo-inspection, recipe-maker]"
        params = {
            "exposure": {"type": "number", "default": 0.1},
            "contrast": {"type": "number", "default": 10.0},
            "quality": {"type": "integer", "default": 92},
        }
        steps = [
            {
                "id": "inspect",
                "tool": "artcraft_inspect",
                "args": {"path": "{input}"},
            },
            {
                "id": "develop",
                "tool": "artcraft_develop",
                "args": {
                    "input_path": "{input}",
                    "output_path": "{output}",
                    "sliders": {
                        "light.exposure": "{params.exposure}",
                        "light.contrast": "{params.contrast}",
                    },
                    "quality": "{params.quality}",
                },
            },
            {
                "id": "review",
                "tool": "artcraft_build_review",
                "args": {
                    "source_path": "{input}",
                    "output_path": "{output}",
                    "working_dir": "{work_dir}/review",
                },
            },
        ]
    elif app == "soundcraft":
        related = "[soundcraft-basics, artcraft-router, recipe-maker]"
        params = {
            "sample_rate": {"type": "integer", "default": 48000},
            "bit_depth": {"type": "string", "default": "24"},
            "normalize": {"type": "boolean", "default": True},
        }
        steps = [
            {
                "id": "probe",
                "tool": "artcraft_audio_basic",
                "args": {"action": "info", "input_path": "{input}"},
            },
            {
                "id": "convert",
                "tool": "artcraft_audio_basic",
                "args": {
                    "action": "convert",
                    "input_path": "{input}",
                    "output_path": "{output}",
                    "sample_rate": "{params.sample_rate}",
                    "bit_depth": "{params.bit_depth}",
                    "normalize": "{params.normalize}",
                },
            },
        ]
    else:  # filmcraft
        related = "[filmcraft-basics, artcraft-router, recipe-maker]"
        params = {
            "quality": {"type": "integer", "default": 85},
            "scale": {"type": "number", "default": 1.0},
        }
        steps = [
            {
                "id": "probe",
                "tool": "artcraft_video_basic",
                "args": {"action": "probe", "input_path": "{input}"},
            },
            {
                "id": "export",
                "tool": "artcraft_video_basic",
                "args": {
                    "action": "export",
                    "input_path": "{input}",
                    "output_path": "{output}",
                    "quality": "{params.quality}",
                    "scale": "{params.scale}",
                },
            },
        ]

    skill_md = (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f'version: "0.1.0"\n'
        f'author: "{author}"\n'
        f'license: "MIT"\n'
        f"platforms: [linux, macos]\n"
        f"metadata:\n"
        f"  hermes:\n"
        f"    category: creative\n"
        f"    tags: [artcraft, recipe, {app}, {media_type}]\n"
        f"    related_skills: {related}\n"
        f"---\n\n"
        f"# Recipe: {title}\n\n"
        f"Run the portable {app} workflow in `recipe.json` without editing source media.\n\n"
        f"## When to Use\n\n"
        f"- Replaying the `{name}` {media_type} recipe across multiple files consistently.\n\n"
        f"## Prerequisites\n\n"
        f"- `{cli_name}` discoverable via `artcraft_status`.\n\n"
        f"## How to Run\n\n"
        f"```bash\n"
        f"hermes artcraft recipe run {name} in{suffix} out{suffix}\n"
        f"```\n\n"
        f"## Procedure\n\n"
        f"1. Inspect `recipe.json` and run `hermes artcraft recipe validate {name}`.\n"
        f"2. Run the recipe into a distinct output path under `<work_dir>/exports/`.\n\n"
        f"## Pitfalls\n\n"
        f"- Never pass the original file path as `output_path`.\n"
        f"- Avoid leaking machine-local paths or host IP addresses before sharing.\n\n"
        f"## Verification\n\n"
        f"- Confirm `source_sha256` remains unchanged and step metrics pass review.\n"
    )

    manifest = {
        "schema_version": "1.0",
        "name": name,
        "title": title,
        "description": description,
        "version": "0.1.0",
        "author": author,
        "license": "MIT",
        "app": app,
        "media_type": media_type,
        "default_output_suffix": suffix,
        "parameters": params,
        "steps": steps,
    }
    return skill_md, manifest


def init_recipe(
    slug: str,
    *,
    app: str = "lightcraft",
    dest_dir: Optional[Union[str, Path]] = None,
    author: str = "wspotter",
    description: Optional[str] = None,
    allow_overwrite: bool = False,
) -> Dict[str, Any]:
    """Scaffold a validated starter `recipe-*` directory with `SKILL.md` and `recipe.json`."""
    if not isinstance(slug, str) or not slug.strip():
        return {"ok": False, "error": "Missing required recipe slug"}

    raw_slug = slug.strip().lower()
    if raw_slug.startswith("recipe-"):
        raw_slug = raw_slug[len("recipe-") :]
    if not _SLUG_RE.fullmatch(raw_slug):
        return {
            "ok": False,
            "error": (
                f"Invalid recipe slug {slug!r}; use lowercase letters, numbers, and hyphens "
                "(2..64 chars)"
            ),
        }

    norm_app = app.strip().lower()
    if norm_app not in SUPPORTED_APPS:
        return {
            "ok": False,
            "error": f"Unsupported app {app!r}; must be one of {list(SUPPORTED_APPS)}",
        }

    if not isinstance(author, str) or not author.strip():
        return {"ok": False, "error": "author must be a non-empty string"}

    dir_name = f"recipe-{raw_slug}"
    title = raw_slug.replace("-", " ").title()
    desc = (description or f"Apply {title.lower()} {APP_MEDIA_TYPES[norm_app]} workflow.").strip()
    if not desc.endswith("."):
        desc += "."
    if len(desc) > 60:
        return {
            "ok": False,
            "error": f"Description exceeds 60 characters ({len(desc)} chars): {desc!r}",
        }

    base_dir = Path(dest_dir).expanduser() if dest_dir else default_user_skills_dir()
    target_dir = base_dir / dir_name
    _ensure_within_dir(target_dir, base_dir, "recipe target directory")

    if os.path.lexists(target_dir) and not allow_overwrite:
        return {
            "ok": False,
            "error": f"Recipe already exists at {target_dir}; pass allow_overwrite=True to replace",
        }

    skill_md, manifest = _starter_template(dir_name, title, norm_app, author.strip(), desc)
    base_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".artcraft-init-", dir=base_dir) as tmp_dir:
        staged = Path(tmp_dir) / dir_name
        staged.mkdir(parents=True, exist_ok=True)
        (staged / "SKILL.md").write_text(skill_md, encoding="utf-8")
        (staged / "recipe.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        val = validate_recipe(staged, require_manifest=True)
        if not val["ok"]:
            return {"ok": False, "error": "Generated template failed validation", **val}

        _install_dir_atomic(staged, target_dir, base_dir, allow_overwrite=allow_overwrite)

    return {
        "ok": True,
        "recipe": dir_name,
        "app": norm_app,
        "recipe_dir": str(target_dir),
        "files": ["SKILL.md", "recipe.json"],
    }


def _install_dir_atomic(
    staged_dir: Path,
    target_dir: Path,
    parent_dir: Path,
    *,
    allow_overwrite: bool,
) -> None:
    """Move `staged_dir` into `target_dir`, safely swapping out prior dir if overwriting."""
    if os.path.lexists(target_dir):
        if not allow_overwrite:
            raise FileExistsError(f"Destination already exists: {target_dir}")
        with tempfile.TemporaryDirectory(prefix=".artcraft-swap-", dir=parent_dir) as backup_dir:
            backup_target = Path(backup_dir) / target_dir.name
            os.replace(target_dir, backup_target)
            try:
                os.replace(staged_dir, target_dir)
            except Exception:
                os.replace(backup_target, target_dir)
                raise
    else:
        os.replace(staged_dir, target_dir)


def _collect_exportable_files(recipe_dir: Path) -> List[Tuple[str, Path]]:
    """Collect safe, non-symlink files allowed in a traded recipe zip bundle."""
    files: List[Tuple[str, Path]] = []
    for entry in sorted(recipe_dir.iterdir()):
        if entry.is_symlink():
            raise ValueError(f"Refusing to pack symlink inside recipe: {entry.name}")
        if entry.name.startswith("."):
            raise ValueError(f"Refusing to pack hidden entry: {entry.name}")
        if entry.is_file():
            if entry.name not in ("SKILL.md", "recipe.json"):
                raise ValueError(
                    f"Unsupported top-level recipe file {entry.name!r}; place assets under assets/"
                )
            if entry.stat().st_size > MAX_RECIPE_FILE_BYTES:
                raise ValueError(f"File exceeds export size limit: {entry.name}")
            files.append((entry.name, entry))
        elif entry.is_dir():
            if entry.name not in ALLOWED_ASSET_SUBDIRS:
                allowed = sorted(ALLOWED_ASSET_SUBDIRS)
                raise ValueError(f"Unsupported subdirectory {entry.name!r}; allowed: {allowed}")
            for root, dirs, names in os.walk(entry, followlinks=False):
                root_p = Path(root)
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for fname in sorted(names):
                    if fname.startswith("."):
                        raise ValueError(f"Refusing to pack hidden asset {fname!r}")
                    fp = root_p / fname
                    if fp.is_symlink():
                        raise ValueError(f"Refusing to pack symlink asset {fp.name!r}")
                    if fp.suffix.lower() not in ALLOWED_ASSET_EXTENSIONS:
                        raise ValueError(f"Disallowed recipe asset extension {fp.suffix!r}")
                    if fp.stat().st_size > MAX_RECIPE_FILE_BYTES:
                        raise ValueError(f"Asset exceeds export size limit: {fp.name}")
                    rel = fp.relative_to(recipe_dir).as_posix()
                    files.append((rel, fp))
    return files


def export_recipe(
    recipe: Union[str, Path],
    archive_path: Union[str, Path],
    *,
    skills_dir: Optional[Union[str, Path]] = None,
    allow_overwrite: bool = False,
) -> Dict[str, Any]:
    """Validate a `recipe-*` directory and export it as a portable zip bundle with checksums."""
    val = validate_recipe(recipe, skills_dir=skills_dir, require_manifest=True)
    if not val["ok"]:
        return {
            "ok": False,
            "error": "Recipe failed validation before export",
            "errors": val.get("errors", []),
            "recipe": val.get("recipe"),
        }

    recipe_dir = Path(val["recipe_dir"])
    recipe_name = val["recipe"]
    out_zip = Path(os.path.abspath(Path(archive_path).expanduser()))
    if _paths_refer_to_same_file(recipe_dir, out_zip):
        return {"ok": False, "error": "archive_path must not point inside recipe directory"}
    if os.path.lexists(out_zip) and not allow_overwrite:
        return {
            "ok": False,
            "error": f"archive_path already exists and allow_overwrite is False: {out_zip}",
        }

    try:
        items = _collect_exportable_files(recipe_dir)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    checksums: Dict[str, str] = {rel: sha256_file(fp) for rel, fp in items}
    checksum_payload = json.dumps(
        {"schema_version": "1.0", "recipe": recipe_name, "files": checksums},
        indent=2,
        sort_keys=True,
    ) + "\n"

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    fixed_dt = (2026, 1, 1, 0, 0, 0)
    with tempfile.TemporaryDirectory(prefix=".artcraft-export-", dir=out_zip.parent) as tmp_dir:
        tmp_zip = Path(tmp_dir) / "bundle.zip"
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for rel, fp in items:
                zi = zipfile.ZipInfo(f"{recipe_name}/{rel}", date_time=fixed_dt)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                zf.writestr(zi, fp.read_bytes())

            c_info = zipfile.ZipInfo(f"{recipe_name}/checksums.json", date_time=fixed_dt)
            c_info.compress_type = zipfile.ZIP_DEFLATED
            c_info.external_attr = 0o644 << 16
            zf.writestr(c_info, checksum_payload.encode("utf-8"))

        if tmp_zip.stat().st_size > MAX_RECIPE_ARCHIVE_BYTES:
            return {"ok": False, "error": "Exported archive exceeds 2 MiB maximum bundle size"}

        atomic_replace_file(tmp_zip, out_zip, allow_overwrite=allow_overwrite)

    return {
        "ok": True,
        "recipe": recipe_name,
        "archive_path": str(out_zip),
        "archive_sha256": sha256_file(out_zip),
        "file_count": len(items) + 1,
        "checksums": checksums,
    }


def _validate_zip_member_path(filename: str) -> Tuple[str, str]:
    """Validate one zip member path against zip-slip, symlinks, and disallowed files."""
    if not filename or "\x00" in filename or "\\" in filename:
        raise ValueError(f"Unsafe zip member path: {filename!r}")
    if filename.startswith("/") or re.match(r"^[A-Za-z]:", filename):
        raise ValueError(f"Absolute path forbidden in zip archive: {filename!r}")
    parts = [p for p in filename.rstrip("/").split("/")]
    if not parts or any(part in ("", ".", "..") or part.startswith(".") for part in parts):
        raise ValueError(f"Path traversal or hidden segment in zip archive: {filename!r}")

    root_name = parts[0]
    if not root_name.startswith("recipe-"):
        raise ValueError(f"Zip bundle root directory must start with 'recipe-', got {root_name!r}")
    _validate_safe_id(root_name, "zip root directory")

    rel = "/".join(parts[1:])
    if not rel:
        return root_name, ""
    if len(parts) == 2:
        if parts[1] not in ALLOWED_BUNDLE_TOP_FILES:
            raise ValueError(f"Unsupported top-level file in bundle: {parts[1]!r}")
    else:
        if parts[1] not in ALLOWED_ASSET_SUBDIRS:
            raise ValueError(f"Unsupported bundle subdirectory: {parts[1]!r}")
        if not filename.endswith("/"):
            ext = Path(parts[-1]).suffix.lower()
            if ext not in ALLOWED_ASSET_EXTENSIONS:
                raise ValueError(f"Unsupported asset extension in bundle: {parts[-1]!r}")
    return root_name, rel


def _read_zip_member_bounded(zf: zipfile.ZipFile, info: zipfile.ZipInfo, budget_left: int) -> bytes:
    """Read a zip entry while strictly enforcing the decompressed byte budget."""
    chunks: List[bytes] = []
    total = 0
    with zf.open(info, "r") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > budget_left:
                raise ValueError("Recipe archive decompressed content exceeds 4 MiB safety limit")
            chunks.append(chunk)
    return b"".join(chunks)


def import_recipe(
    archive_path: Union[str, Path],
    *,
    dest_dir: Optional[Union[str, Path]] = None,
    allow_overwrite: bool = False,
) -> Dict[str, Any]:
    """Safely inspect, validate checksums/rules, and install a traded recipe zip bundle."""
    arch_p = Path(archive_path).expanduser()
    if not arch_p.is_file():
        return {"ok": False, "error": f"Archive file does not exist: {arch_p}"}
    if arch_p.stat().st_size > MAX_RECIPE_ARCHIVE_BYTES:
        return {"ok": False, "error": "Archive file exceeds 2 MiB size limit"}

    base_dir = Path(dest_dir).expanduser() if dest_dir else default_user_skills_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(arch_p, "r") as zf:
            infos = zf.infolist()
            if not infos:
                return {"ok": False, "error": "Recipe archive is empty"}

            root_names: set[str] = set()
            budget = MAX_RECIPE_EXTRACTED_BYTES
            with tempfile.TemporaryDirectory(prefix=".artcraft-import-", dir=base_dir) as tmp_dir:
                tmp_root = Path(tmp_dir)
                extracted_checksums: Optional[Dict[str, Any]] = None
                verified_files: List[str] = []

                for info in infos:
                    mode = (info.external_attr >> 16) & 0o170000
                    if mode == stat.S_IFLNK:
                        raise ValueError(f"Symlink entries are forbidden in zip: {info.filename!r}")
                    if info.file_size > MAX_RECIPE_EXTRACTED_BYTES:
                        raise ValueError(f"Zip entry too large: {info.filename!r}")

                    root_name, rel = _validate_zip_member_path(info.filename)
                    root_names.add(root_name)
                    if len(root_names) > 1:
                        raise ValueError(
                            "Recipe archive must contain a single recipe-* root folder"
                        )

                    if info.is_dir() or not rel:
                        continue

                    data = _read_zip_member_bounded(zf, info, budget)
                    budget -= len(data)
                    out_file = tmp_root / root_name / rel
                    _ensure_within_dir(out_file, tmp_root, "imported archive entry")
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    out_file.write_bytes(data)

                    if rel == "checksums.json":
                        extracted_checksums = json.loads(data.decode("utf-8"))
                    else:
                        verified_files.append(rel)

                recipe_name = next(iter(root_names))
                staged_dir = tmp_root / recipe_name
                if not staged_dir.is_dir():
                    return {"ok": False, "error": "Archive contained no extractable recipe files"}

                if extracted_checksums is not None:
                    expected_map = extracted_checksums.get("files")
                    if not isinstance(expected_map, dict):
                        raise ValueError("Invalid checksums.json inside archive")
                    for rel_p in ("SKILL.md", "recipe.json"):
                        if rel_p not in expected_map:
                            raise ValueError(f"checksums.json missing required entry {rel_p!r}")
                    for rel_p, exp_sha in expected_map.items():
                        target_f = staged_dir / rel_p
                        _ensure_within_dir(target_f, staged_dir, "checksum entry")
                        if not target_f.is_file() or sha256_file(target_f) != exp_sha:
                            raise ValueError(f"Checksum mismatch for {rel_p!r} inside archive")

                # Never install checksums.json as clutter if unnecessary, validate full skill first
                checksums_file = staged_dir / "checksums.json"
                if os.path.lexists(checksums_file):
                    checksum_bak = tmp_root / "_checksums.json"
                    os.replace(checksums_file, checksum_bak)

                val = validate_recipe(staged_dir, require_manifest=True)
                if not val["ok"]:
                    return {
                        "ok": False,
                        "error": "Imported recipe failed safety/schema validation",
                        "errors": val.get("errors", []),
                    }

                target_dir = base_dir / recipe_name
                _ensure_within_dir(target_dir, base_dir, "installed recipe destination")
                if os.path.lexists(target_dir) and not allow_overwrite:
                    return {
                        "ok": False,
                        "error": (
                            f"Recipe {recipe_name!r} already exists at {target_dir}; "
                            "pass allow_overwrite=True to replace"
                        ),
                    }
                _install_dir_atomic(
                    staged_dir, target_dir, base_dir, allow_overwrite=allow_overwrite
                )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "recipe": recipe_name,
        "recipe_dir": str(target_dir),
        "files": sorted(verified_files),
    }


def _coerce_param(name: str, raw: Any, ptype: str) -> Any:
    """Coerce and type-check an override parameter against the manifest type."""
    if raw is None:
        return None
    if ptype == "boolean":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.lower() in ("true", "false"):
            return raw.lower() == "true"
        raise ValueError(f"Parameter '{name}' must be boolean, got {raw!r}")
    if ptype == "integer":
        if isinstance(raw, bool):
            raise ValueError(f"Parameter '{name}' must be integer, got {raw!r}")
        if isinstance(raw, float) and not raw.is_integer():
            raise ValueError(f"Parameter '{name}' must be integer, got {raw!r}")
        return int(raw)
    if ptype == "number":
        if isinstance(raw, bool):
            raise ValueError(f"Parameter '{name}' must be number, got {raw!r}")
        val = float(raw)
        if not math.isfinite(val):
            raise ValueError(f"Parameter '{name}' must be finite, got {raw!r}")
        return val
    if ptype == "string":
        if isinstance(raw, (dict, list, bool)):
            raise ValueError(f"Parameter '{name}' must be string, got {raw!r}")
        return str(raw)
    if ptype == "array":
        if not isinstance(raw, list):
            raise ValueError(f"Parameter '{name}' must be array/list, got {type(raw).__name__}")
        return list(raw)
    if ptype == "object":
        if not isinstance(raw, dict):
            raise ValueError(f"Parameter '{name}' must be object/dict, got {type(raw).__name__}")
        return dict(raw)
    return raw


def _resolve_params(
    declared: Dict[str, Any],
    overrides: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge default manifest parameters with caller overrides and type-validate all."""
    effective: Dict[str, Any] = {}
    for name, spec in declared.items():
        if "default" in spec:
            effective[name] = _coerce_param(name, spec["default"], spec["type"])
        else:
            effective[name] = None

    if overrides:
        if not isinstance(overrides, dict):
            raise ValueError("params must be an object/dict")
        for key, raw in overrides.items():
            if key not in declared:
                raise ValueError(
                    f"Unknown parameter {key!r}; supported parameters: {sorted(declared)}"
                )
            effective[key] = _coerce_param(key, raw, declared[key]["type"])
    return effective


def _resolve_template_value(
    val: Any,
    *,
    ctx_paths: Dict[str, str],
    params: Dict[str, Any],
) -> Any:
    """Resolve placeholders recursively while preserving exact scalar/collection types."""
    if isinstance(val, str):
        full = _PLACEHOLDER_RE.fullmatch(val)
        if full:
            tok = full.group(1)
            if tok in ctx_paths:
                return ctx_paths[tok]
            if tok.startswith("params."):
                return params.get(tok[len("params.") :])
            raise ValueError(f"Unknown placeholder '{{{tok}}}'")

        def _repl(match: re.Match[str]) -> str:
            tok = match.group(1)
            if tok in ctx_paths:
                return ctx_paths[tok]
            if tok.startswith("params."):
                resolved_p = params.get(tok[len("params.") :])
                if resolved_p is None:
                    raise ValueError(f"Required string parameter '{tok}' is unset")
                return str(resolved_p)
            raise ValueError(f"Unknown placeholder '{{{tok}}}'")

        return _PLACEHOLDER_RE.sub(_repl, val)

    if isinstance(val, list):
        return [
            _resolve_template_value(item, ctx_paths=ctx_paths, params=params) for item in val
        ]

    if isinstance(val, dict):
        out: Dict[str, Any] = {}
        for k, v in val.items():
            resolved = _resolve_template_value(v, ctx_paths=ctx_paths, params=params)
            if resolved is not None:
                out[k] = resolved
        return out

    return val


def _verify_resolved_step_paths(
    step_id: str,
    resolved_args: Dict[str, Any],
    *,
    in_path: Path,
    staging_out: Path,
    work_dir: Path,
) -> None:
    """Enforce path containment on resolved step arguments before invoking any tool."""
    res_in = in_path.resolve()
    res_stage = staging_out.resolve()
    res_work = work_dir.resolve()

    for key in PATH_ARG_KEYS:
        if key not in resolved_args:
            continue
        raw_p = resolved_args[key]
        if raw_p is None:
            continue
        cand = Path(str(raw_p)).resolve()

        if cand == res_in:
            if key in WRITE_PATH_KEYS:
                raise ValueError(f"Step '{step_id}' arg '{key}' cannot target source input_path")
            continue
        if cand == res_stage:
            continue
        if key == "working_dir" and cand == res_work:
            continue
        _ensure_within_dir(cand, work_dir, f"step '{step_id}' arg '{key}'")


def _step_succeeded(tool_name: str, res: Dict[str, Any]) -> bool:
    """Determine whether a dispatched ArtCraft tool result succeeded."""
    if res.get("status") in ("needs_decision", "needs_clarification"):
        return False
    if res.get("ok") is False:
        return False
    if "ok" not in res and not res.get("passed", False):
        return False
    if (
        tool_name in ("artcraft_verify_edit", "artcraft_build_review")
        and res.get("passed") is False
    ):
        return False
    return True


def run_recipe(
    recipe: Union[str, Path],
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    *,
    params: Optional[Dict[str, Any]] = None,
    work_dir: Optional[Union[str, Path]] = None,
    skills_dir: Optional[Union[str, Path]] = None,
    allow_overwrite: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Validate and deterministically replay a multi-step `recipe-*` workflow."""
    in_p = Path(input_path).expanduser()
    if not in_p.is_file():
        return {"ok": False, "status": "error", "error": f"input_path does not exist: {input_path}"}
    in_resolved = in_p.resolve()
    source_sha256 = sha256_file(in_resolved)

    out_p = Path(os.path.abspath(Path(output_path).expanduser()))
    if _paths_refer_to_same_file(in_resolved, out_p):
        return {
            "ok": False,
            "status": "error",
            "source_sha256": source_sha256,
            "error": "output_path must be distinct from input_path to preserve source",
        }
    if os.path.lexists(out_p) and not allow_overwrite:
        return {
            "ok": False,
            "status": "error",
            "source_sha256": source_sha256,
            "error": f"output_path already exists and allow_overwrite is False: {out_p}",
        }

    val = validate_recipe(recipe, skills_dir=skills_dir, require_manifest=True)
    if not val["ok"] or not isinstance(val.get("manifest"), dict):
        return {
            "ok": False,
            "status": "error",
            "source_sha256": source_sha256,
            "error": "Recipe failed validation",
            "errors": val.get("errors", []),
        }

    manifest = val["manifest"]
    try:
        effective_params = _resolve_params(manifest.get("parameters", {}), params)
    except ValueError as exc:
        return {
            "ok": False,
            "status": "error",
            "source_sha256": source_sha256,
            "error": str(exc),
        }

    from . import tools as _tools  # Late import avoids circular dependency with tools.py

    with ExitStack() as stack:
        if work_dir is not None:
            wdir = Path(os.path.abspath(Path(work_dir).expanduser()))
            wdir.mkdir(parents=True, exist_ok=True)
        else:
            wdir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="artcraft-recipe-")))

        stage_dir = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix=".stage-", dir=wdir))
        )
        suffix = out_p.suffix or manifest.get("default_output_suffix") or ".bin"
        staging_out = stage_dir / f"output{suffix}"
        ctx_paths = {
            "input": str(in_resolved),
            "output": str(staging_out),
            "work_dir": str(wdir),
        }

        planned_steps: List[Dict[str, Any]] = []
        for step in manifest["steps"]:
            step_id = step["id"]
            tool_name = step["tool"]
            if tool_name not in ALLOWED_RECIPE_TOOL_NAMES:
                return {
                    "ok": False,
                    "status": "error",
                    "source_sha256": source_sha256,
                    "error": f"Disallowed recipe step tool {tool_name!r}",
                }
            resolved_args = _resolve_template_value(
                step["args"], ctx_paths=ctx_paths, params=effective_params
            )
            _verify_resolved_step_paths(
                step_id,
                resolved_args,
                in_path=in_resolved,
                staging_out=staging_out,
                work_dir=wdir,
            )
            planned_steps.append({"id": step_id, "tool": tool_name, "args": resolved_args})

        if dry_run:
            return {
                "ok": True,
                "status": "dry_run",
                "dry_run": True,
                "recipe": manifest["name"],
                "app": manifest["app"],
                "input_path": str(in_resolved),
                "output_path": str(out_p),
                "source_sha256": source_sha256,
                "params": effective_params,
                "planned_steps": planned_steps,
            }

        step_results: List[Dict[str, Any]] = []
        for entry in planned_steps:
            step_id = entry["id"]
            tool_name = entry["tool"]
            tool_fn = getattr(_tools, tool_name, None)
            if tool_fn is None:
                return {
                    "ok": False,
                    "status": "error",
                    "source_sha256": source_sha256,
                    "error": f"Registered tool handler missing: {tool_name}",
                }

            raw_res = tool_fn(entry["args"])
            res = json.loads(raw_res) if isinstance(raw_res, str) else dict(raw_res)
            step_results.append({"id": step_id, "tool": tool_name, "result": res})

            if sha256_file(in_resolved) != source_sha256:
                return {
                    "ok": False,
                    "status": "error",
                    "failed_step": step_id,
                    "error": "non_destructive_violation: input_path SHA-256 changed during replay",
                    "steps": step_results,
                }

            gate_status = res.get("status")
            if gate_status in ("needs_decision", "needs_clarification"):
                return {
                    "ok": False,
                    "status": gate_status,
                    "recipe": manifest["name"],
                    "failed_step": step_id,
                    "reason": res.get("reason") or res.get("error"),
                    "gate_category": res.get("gate_category"),
                    "source_sha256": source_sha256,
                    "original_intact": True,
                    "steps": step_results,
                }

            if not _step_succeeded(tool_name, res):
                return {
                    "ok": False,
                    "status": "error",
                    "recipe": manifest["name"],
                    "failed_step": step_id,
                    "error": (
                        res.get("error")
                        or res.get("reason")
                        or res.get("summary")
                        or f"Step '{step_id}' failed"
                    ),
                    "source_sha256": source_sha256,
                    "original_intact": True,
                    "steps": step_results,
                }

        if not staging_out.is_file() or staging_out.stat().st_size == 0:
            return {
                "ok": False,
                "status": "error",
                "recipe": manifest["name"],
                "source_sha256": source_sha256,
                "error": "Recipe completed without writing a non-empty output file",
                "steps": step_results,
            }

        staged_sha = sha256_file(staging_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".promote-", dir=out_p.parent) as promote_dir:
            local_tmp = Path(promote_dir) / out_p.name
            shutil.copy2(staging_out, local_tmp)
            if sha256_file(local_tmp) != staged_sha:
                raise RuntimeError("Staging checksum verification failed before promotion")
            atomic_replace_file(local_tmp, out_p, allow_overwrite=allow_overwrite)

    return {
        "ok": True,
        "status": "completed",
        "recipe": manifest["name"],
        "app": manifest["app"],
        "input_path": str(in_resolved),
        "output_path": str(out_p),
        "work_dir": str(wdir),
        "source_sha256": source_sha256,
        "output_sha256": sha256_file(out_p),
        "params": effective_params,
        "steps": step_results,
    }
