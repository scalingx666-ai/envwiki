"""Tests for the command line surface."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from envwiki.cli import app

runner = CliRunner()


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


def test_there_is_no_build_command_any_more():
    """envwiki must not orchestrate synthesis: the agent drives the MCP server."""
    result = runner.invoke(app, ["build", "https://example.com"])
    assert result.exit_code != 0


def test_validate_reports_a_broken_task(tmp_path: Path):
    task = tmp_path / "task"
    task.mkdir()
    result = runner.invoke(app, ["validate", str(task)])
    assert result.exit_code == 1
    assert "task.toml" in result.stdout


def test_mcp_config_prints_the_server_entry():
    result = runner.invoke(app, ["mcp", "config"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    entry = payload["mcpServers"]["envwiki"]
    assert entry["args"] == ["-m", "envwiki.mcp_server"]
    assert entry["command"]


def test_skill_install_copies_the_skill(tmp_path: Path):
    target = tmp_path / "skills"
    result = runner.invoke(app, ["skill", "install", "--to", str(target)])
    assert result.exit_code == 0
    assert (target / "env-synthesis" / "SKILL.md").is_file()


def test_skill_install_without_target_prints_the_source(tmp_path: Path):
    result = runner.invoke(app, ["skill", "install"])
    assert result.exit_code == 0
    assert "env-synthesis" in result.stdout
