"""Tests for the skill that carries the method."""

from __future__ import annotations

from envwiki.skills import builtin_skill_dirs


def _skill_body() -> str:
    directories = builtin_skill_dirs()
    assert directories
    return (directories[0] / "SKILL.md").read_text(encoding="utf-8")


def test_builtin_skill_has_valid_frontmatter():
    for directory in builtin_skill_dirs():
        body = (directory / "SKILL.md").read_text(encoding="utf-8")
        head = body.split("---")[1]
        assert "name:" in head
        assert "description:" in head


def test_skill_carries_the_whole_workflow():
    body = _skill_body()
    for tool in (
        "stage_source",
        "plan_task",
        "get_recipe",
        "scaffold_task",
        "validate_task",
    ):
        assert tool in body
    assert "/logs/verifier/reward.txt" in body


def test_skill_does_not_carry_a_task_spec():
    """The method lives here; the shape of a task lives in the tool signature."""
    body = _skill_body()
    assert "schema_version" not in body
    assert "task.toml" not in body
