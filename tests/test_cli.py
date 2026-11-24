"""Tests for the command line surface."""

from __future__ import annotations

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


def test_build_without_inputs_exits_with_error():
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 2
