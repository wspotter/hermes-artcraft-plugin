"""Automated tests enforcing Hermes skill authoring standards and portability hygiene."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
README_PATH = REPO_ROOT / "README.md"

EXPECTED_SKILLS = {
    "artcraft-router",
    "filmcraft-basics",
    "lightcraft-basics",
    "lightcraft-cli-edits",
    "photo-inspection",
    "photo-restoration",
    "photocraft-cli-edits",
    "print-preparation",
    "recipe-color-cast",
    "recipe-dust-scratches",
    "recipe-enlargement",
    "recipe-faded-tones",
    "recipe-maker",
    "recipe-noise-grain",
    "recipe-sharpening",
    "soundcraft-basics",
}

BANNED_MARKETING = re.compile(
    r"\b(powerful|comprehensive|seamless|advanced|revolutionary|cutting-edge|state-of-the-art)\b",
    re.IGNORECASE,
)

MACHINE_LOCAL_PATH = re.compile(
    r"/home/(?!runner\b)[a-z0-9_-]+/|[A-Z]:\\+Users\\+(?!<)",
    re.IGNORECASE,
)

RFC1918_IP = re.compile(
    r"(?<![0-9.])(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![0-9.])"
)


def _forbidden_terms_pattern() -> re.Pattern[str] | None:
    raw = os.environ.get("ARTCRAFT_FORBIDDEN_TERMS", "").strip()
    if not raw:
        return None
    terms = [re.escape(part.strip()) for part in re.split(r"[,|]", raw) if part.strip()]
    if not terms:
        return None
    return re.compile(r"\b(?:" + "|".join(terms) + r")\b", re.IGNORECASE)

SHELL_FENCE_OPEN = re.compile(
    r"^\s*(`{3,}|~{3,})\s*(bash|sh|shell|zsh|console)\b",
    re.IGNORECASE,
)

CONTINUATION_THEN_COMMENT = re.compile(r"\\\s+#")
RAW_SHELL_TOOLS = re.compile(r"\b(grep|cat|head|tail|sed|awk|find|ls)\b")
HARDCODED_TMP = re.compile(r"(?<![a-zA-Z0-9_])/tmp\b")
REQUIRED_SECTIONS = (
    "## When to Use",
    "## Prerequisites",
    "## How to Run",
    "## Procedure",
    "## Pitfalls",
    "## Verification",
)


def _parse_skill(path: Path) -> tuple[dict, str]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise AssertionError(f"{path}: SKILL.md must start with YAML frontmatter '---'")
    match = re.search(r"\n---\s*\n", content[3:])
    if not match:
        raise AssertionError(f"{path}: unclosed YAML frontmatter")
    raw_fm = content[3 : match.start() + 3]
    frontmatter = yaml.safe_load(raw_fm)
    if not isinstance(frontmatter, dict):
        raise AssertionError(f"{path}: YAML frontmatter must parse to a dict")
    return frontmatter, content


class SkillStandardsTest(unittest.TestCase):
    """Verify every bundled SKILL.md follows Hermes skill packaging and portability conventions."""

    def test_expected_skill_directories_exist(self) -> None:
        skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
        found_names = {p.parent.name for p in skill_files}
        self.assertEqual(found_names, EXPECTED_SKILLS)

    def test_frontmatter_and_description_rules(self) -> None:
        skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
        all_skill_names = {p.parent.name for p in skill_files}

        for skill_path in skill_files:
            rel = skill_path.relative_to(REPO_ROOT)
            with self.subTest(skill=str(rel)):
                fm, content = _parse_skill(skill_path)

                for required in (
                    "name",
                    "description",
                    "version",
                    "author",
                    "license",
                    "platforms",
                    "metadata",
                ):
                    self.assertIn(required, fm, f"{rel}: missing frontmatter key {required!r}")

                self.assertEqual(
                    fm["name"],
                    skill_path.parent.name,
                    (
                        f"{rel}: frontmatter name {fm['name']!r} "
                        f"!= directory {skill_path.parent.name!r}"
                    ),
                )
                self.assertEqual(fm["version"], "0.1.0")
                self.assertEqual(fm["author"], "wspotter")
                self.assertEqual(fm["license"], "MIT")
                self.assertEqual(fm["platforms"], ["linux", "macos"])

                hermes_meta = (fm.get("metadata") or {}).get("hermes") or {}
                self.assertEqual(
                    hermes_meta.get("category"),
                    "creative",
                    f"{rel}: metadata.hermes.category must be 'creative'",
                )
                tags = hermes_meta.get("tags")
                self.assertIsInstance(tags, list, f"{rel}: metadata.hermes.tags must be a list")
                self.assertGreater(len(tags), 0, f"{rel}: metadata.hermes.tags must not be empty")

                related = hermes_meta.get("related_skills") or []
                for rel_skill in related:
                    self.assertIn(
                        rel_skill,
                        all_skill_names,
                        f"{rel}: dangling related_skills entry {rel_skill!r}",
                    )

                desc = str(fm["description"])
                self.assertLessEqual(
                    len(desc),
                    60,
                    f"{rel}: description is {len(desc)} chars (must be <= 60): {desc!r}",
                )
                self.assertTrue(
                    desc.endswith("."),
                    f"{rel}: description must end with a period: {desc!r}",
                )
                self.assertIsNone(
                    BANNED_MARKETING.search(desc),
                    f"{rel}: banned marketing word in description: {desc!r}",
                )
                self.assertNotIn(
                    fm["name"].lower(),
                    desc.lower(),
                    f"{rel}: description must not repeat skill name {fm['name']!r}",
                )
                self.assertNotIn(
                    hermes_meta["category"].lower(),
                    desc.lower(),
                    f"{rel}: description must not repeat category {hermes_meta['category']!r}",
                )

                # Also check the raw regex check from skills/AGENTS.md:
                raw_desc_match = re.search(r"^description: (.*)$", content, re.M)
                self.assertIsNotNone(raw_desc_match, f"{rel}: single-line description required")
                self.assertLessEqual(len(raw_desc_match.group(1).strip("\"'")), 60)

    def test_no_machine_paths_or_private_ips(self) -> None:
        paths_to_check = sorted(SKILLS_DIR.glob("*/SKILL.md")) + [README_PATH]
        forbidden_re = _forbidden_terms_pattern()
        for path in paths_to_check:
            rel = path.relative_to(REPO_ROOT)
            with self.subTest(file=str(rel)):
                content = path.read_text(encoding="utf-8")
                path_match = MACHINE_LOCAL_PATH.search(content)
                self.assertIsNone(
                    path_match,
                    (
                        f"{rel}: found machine-local path {path_match.group(0)!r}"
                        if path_match
                        else ""
                    ),
                )
                ip_match = RFC1918_IP.search(content)
                self.assertIsNone(
                    ip_match,
                    f"{rel}: found private RFC1918 IP {ip_match.group(0)!r}" if ip_match else "",
                )
                if forbidden_re is not None:
                    term_match = forbidden_re.search(content)
                    self.assertIsNone(
                        term_match,
                        (
                            f"{rel}: found forbidden term {term_match.group(0)!r}"
                            if term_match
                            else ""
                        ),
                    )

    def test_shell_fences_are_paste_safe(self) -> None:
        for skill_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            rel = skill_path.relative_to(REPO_ROOT)
            content = skill_path.read_text(encoding="utf-8")
            fence = None
            for lineno, line in enumerate(content.splitlines(), 1):
                if fence is None:
                    m = SHELL_FENCE_OPEN.match(line)
                    if m:
                        fence = m.group(1)
                    continue
                if line.strip().startswith(fence):
                    fence = None
                    continue
                self.assertIsNone(
                    CONTINUATION_THEN_COMMENT.search(line),
                    f"{rel}:{lineno}: comment after backslash continuation breaks pasted commands",
                )

    def test_modern_sections_and_no_shell_or_tmp_antipatterns(self) -> None:
        for skill_path in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            rel = skill_path.relative_to(REPO_ROOT)
            with self.subTest(skill=str(rel)):
                _, content = _parse_skill(skill_path)
                for section in REQUIRED_SECTIONS:
                    self.assertIn(section, content, f"{rel}: missing required section {section!r}")
                self.assertIsNone(
                    RAW_SHELL_TOOLS.search(content),
                    f"{rel}: contains raw shell utility anti-pattern",
                )
                self.assertIsNone(
                    HARDCODED_TMP.search(content),
                    f"{rel}: contains hardcoded /tmp path",
                )


if __name__ == "__main__":
    unittest.main()
