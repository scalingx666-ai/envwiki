"""Skill files that envwiki ships.

A skill is a directory holding a SKILL.md file with name and description
frontmatter. An agent loads it when the work matches; envwiki itself only
ships it and can install it somewhere an agent will look.
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
