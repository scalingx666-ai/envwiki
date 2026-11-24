"""Tests for task synthesis, rendering and validation."""

from __future__ import annotations

from pathlib import Path

from envwiki.convert.builder import (
    asset_destinations,
    render_dockerfile,
    render_task_toml,
    write_task,
)
from envwiki.convert.validate import validate_task
from envwiki.schemas import (
    EnvironmentSpec,
    SolutionSpec,
    TaskDraft,
    TaskMetadata,
    VerifierSpec,
)

BASH_VERIFIER = (
    "#!/bin/bash" + chr(10)
    + "mkdir -p /logs/verifier" + chr(10)
    + "echo 1 > /logs/verifier/reward.txt" + chr(10)
    + "test -f /app/out.txt" + chr(10)
)


def _draft(**overrides) -> TaskDraft:
    data = dict(
        name="demo-task",
        description="A demo task.",
        metadata=TaskMetadata(difficulty="easy", category="demo", tags=["x"]),
        instruction_md="Do the thing.",
        environment=EnvironmentSpec(base_image="ubuntu:24.04", workdir="/app"),
        verifier=VerifierSpec(language="bash", code=BASH_VERIFIER),
        solution=SolutionSpec(
            language="bash", code="#!/bin/bash" + chr(10) + "echo hi > /app/out.txt" + chr(10)
        ),
    )
    data.update(overrides)
    return TaskDraft(**data)


def test_task_name_uses_org_format():
    toml_text = render_task_toml(_draft())
    assert 'name = "envwiki/demo-task"' in toml_text
    assert 'schema_version = "1.4"' in toml_text


def test_asset_destinations_flattens_to_file_name():
    draft = _draft()
    draft.environment.copy_from_staging = ["repos/owner-name/readme.md"]
    assert asset_destinations(draft) == {"repos/owner-name/readme.md": "readme.md"}


def test_asset_destinations_keeps_structure_on_collision():
    draft = _draft()
    draft.environment.copy_from_staging = ["a/readme.md", "b/readme.md"]
    mapping = asset_destinations(draft)
    assert mapping["a/readme.md"] == "readme.md"
    assert mapping["b/readme.md"] == "b/readme.md"


def test_dockerfile_copies_into_workdir():
    draft = _draft()
    draft.environment.copy_from_staging = ["repos/o/readme.md"]
    dockerfile = render_dockerfile(draft)
    assert "FROM ubuntu:24.04" in dockerfile
    assert "COPY readme.md /app/readme.md" in dockerfile
    assert "WORKDIR /app" in dockerfile


def test_write_task_creates_expected_layout(tmp_path: Path):
    draft = _draft()
    task_dir = write_task(draft, tmp_path / "task")
    assert (task_dir / "task.toml").is_file()
    assert (task_dir / "instruction.md").is_file()
    assert (task_dir / "environment" / "Dockerfile").is_file()
    assert (task_dir / "tests" / "test.sh").is_file()
    assert (task_dir / "solution" / "solve.sh").is_file()
    assert (task_dir / "envwiki.json").is_file()
    assert (task_dir / "tests" / "test.sh").stat().st_mode & 0o111


def test_write_task_adds_reward_fallback(tmp_path: Path):
    draft = _draft()
    draft.verifier.code = "test -f /app/out.txt" + chr(10)
    task_dir = write_task(draft, tmp_path / "task")
    code = (task_dir / "tests" / "test.sh").read_text(encoding="utf-8")
    assert "/logs/verifier/reward.txt" in code
    assert code.index("reward.txt") < code.index("test -f /app/out.txt")


def test_write_task_copies_staged_asset_into_build_context(tmp_path: Path):
    staging = tmp_path / "staging"
    (staging / "repos" / "o").mkdir(parents=True)
    (staging / "repos" / "o" / "readme.md").write_text("body", encoding="utf-8")

    draft = _draft()
    draft.environment.copy_from_staging = ["repos/o/readme.md"]
    task_dir = write_task(draft, tmp_path / "task", staging_dir=staging)

    copied = task_dir / "environment" / "readme.md"
    assert copied.is_file()
    assert copied.read_text(encoding="utf-8") == "body"


def test_write_task_keeps_unrelated_files_in_the_directory(tmp_path: Path):
    out = tmp_path / "task"
    out.mkdir()
    keep = out / "notes.md"
    keep.write_text("keep me", encoding="utf-8")

    write_task(_draft(), out)

    assert keep.read_text(encoding="utf-8") == "keep me"
    assert (out / "task.toml").is_file()


def test_write_task_replaces_stale_files_of_the_task(tmp_path: Path):
    out = tmp_path / "task"
    write_task(_draft(), out)
    (out / "tests" / "test.py").write_text("stale", encoding="utf-8")

    write_task(_draft(), out)

    assert not (out / "tests" / "test.py").exists()
    assert (out / "tests" / "test.sh").is_file()


def test_task_provenance_records_the_recipe_used(tmp_path: Path):
    draft = _draft()
    draft.source_notes = "Grounded in the paper, following dockerized-terminal-blueprint."
    task_dir = write_task(draft, tmp_path / "task")
    import json

    meta = json.loads((task_dir / "envwiki.json").read_text(encoding="utf-8"))
    assert "dockerized-terminal-blueprint" in meta["recipes"]


def test_validate_accepts_generated_task(tmp_path: Path):
    task_dir = write_task(_draft(), tmp_path / "task")
    report = validate_task(task_dir)
    assert report.ok, [i.message for i in report.errors]


def test_validate_rejects_bad_task_name(tmp_path: Path):
    task_dir = write_task(_draft(), tmp_path / "task")
    toml_path = task_dir / "task.toml"
    toml_path.write_text(
        toml_path.read_text(encoding="utf-8").replace(
            'name = "envwiki/demo-task"', 'name = "demo-task"'
        ),
        encoding="utf-8",
    )
    report = validate_task(task_dir)
    assert not report.ok
    assert any("org/name" in issue.message for issue in report.errors)


def test_validate_flags_missing_instruction(tmp_path: Path):
    task_dir = write_task(_draft(), tmp_path / "task")
    (task_dir / "instruction.md").unlink()
    report = validate_task(task_dir)
    assert not report.ok
    assert any("instruction.md" in issue.message for issue in report.errors)



