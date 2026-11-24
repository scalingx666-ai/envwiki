"""Skill files that envwiki injects into the harness.

A skill is a directory holding a SKILL.md file with name and description
frontmatter. The harness advertises it, and the model loads it when the work
matches.
"""

from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent


def builtin_skill_dirs() -> list[Path]:
    """Every skill shipped with envwiki."""
    if not SKILLS_DIR.is_dir():
        return []
    return [
        entry
        for entry in sorted(SKILLS_DIR.iterdir())
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    ]
