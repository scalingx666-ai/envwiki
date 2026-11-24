"""Tests for the command line surface."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from envwiki.cli import app
from envwiki.harness.base import HarnessResult

runner = CliRunner()

TASK_TOML = """schema_version = "1.4"

[task]
name = "envwiki/demo-task"

[metadata]
difficulty = "easy"
category = "demo"

[verifier]
timeout_sec = 900.0

[environment]
os = "linux"
workdir = "/app"
"""

VERIFIER = (
    "#!/bin/bash" + chr(10)
    + "mkdir -p /logs/verifier" + chr(10)
    + "echo 1 > /logs/verifier/reward.txt" + chr(10)
    + "test -f /app/out.txt" + chr(10)
)


class FakeAgent:
    """A harness that behaves like an agent that wrote one task."""

    def __init__(self, config, allow_write_tools: bool = False) -> None:
        self.config = config
        self.allow_write_tools = allow_write_tools
        self.cwd: Path | None = None

    def prepare(self, cwd, **kwargs) -> None:
        self.cwd = Path(cwd)

    def run(self, prompt, **kwargs) -> HarnessResult:
        task = self.cwd / "tasks" / "demo-task"
        (task / "environment").mkdir(parents=True)
        (task / "tests").mkdir(parents=True)
        (task / "task.toml").write_text(TASK_TOML, encoding="utf-8")
        (task / "instruction.md").write_text("Do the thing." + chr(10), encoding="utf-8")
        (task / "environment" / "Dockerfile").write_text(
            "FROM ubuntu:24.04" + chr(10), encoding="utf-8"
        )
        (task / "tests" / "test.sh").write_text(VERIFIER, encoding="utf-8")
        return HarnessResult("the task is written", True)


class SilentAgent(FakeAgent):
    """A harness that wrote nothing at all."""

    def run(self, prompt, **kwargs) -> HarnessResult:
        return HarnessResult("I could not build anything", True)


def test_inspect_reports_github_strategy():
    result = runner.invoke(
        app, ["inspect", "https://github.com/scalingx666-ai/awesome-environment"]
    )
    assert result.exit_code == 0
    assert "git clone" in result.stdout
    assert "scalingx666-ai" in result.stdout


def test_inspect_reports_reader_strategy():
    result = runner.invoke(app, ["inspect", "https://example.com/page"])
    assert result.exit_code == 0
    assert "reader" in result.stdout


def test_build_without_inputs_exits_with_error():
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 2


def test_build_publishes_the_task_the_agent_wrote(tmp_path, monkeypatch):
    material = tmp_path / "notes.md"
    material.write_text("some material", encoding="utf-8")
    monkeypatch.setattr("envwiki.cli.PiHarness", FakeAgent)

    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "build",
            "--upload",
            str(material),
            "--out",
            str(out),
            "--workspace",
            str(tmp_path / "workspace"),
            "--no-register",
        ],
    )

    assert result.exit_code == 0, result.output
    published = out / "demo-task"
    assert (published / "task.toml").is_file()
    assert (published / "instruction.md").is_file()
    assert "validation: ok" in result.output


def test_build_fails_when_the_agent_wrote_no_task(tmp_path, monkeypatch):
    material = tmp_path / "notes.md"
    material.write_text("some material", encoding="utf-8")
    monkeypatch.setattr("envwiki.cli.PiHarness", SilentAgent)

    result = runner.invoke(
        app,
        [
            "build",
            "--upload",
            str(material),
            "--out",
            str(tmp_path / "out"),
            "--workspace",
            str(tmp_path / "workspace"),
            "--no-register",
        ],
    )

    assert result.exit_code == 1
    assert not (tmp_path / "out" / "demo-task").exists()
