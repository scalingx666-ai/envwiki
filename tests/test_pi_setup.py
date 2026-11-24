"""Tests for the pi wiring helpers."""

from __future__ import annotations

from pathlib import Path

from envwiki.config import ModelEndpoint
from envwiki.pi_setup import mcp_server_entry, register_provider


def test_register_provider_is_idempotent_and_keeps_secrets_out(tmp_path: Path):
    agent_dir = tmp_path / "agent"
    endpoint = ModelEndpoint.from_env(api_key="super-secret-value")

    first = register_provider(agent_dir, endpoint)
    assert first.changed

    body = (agent_dir / "models.json").read_text(encoding="utf-8")
    assert "super-secret-value" not in body
    assert "$ENVWIKI_API_KEY" in body

    second = register_provider(agent_dir, endpoint)
    assert not second.changed


def test_register_provider_dry_run_writes_nothing(tmp_path: Path):
    agent_dir = tmp_path / "agent"
    result = register_provider(agent_dir, ModelEndpoint.from_env(), dry_run=True)
    assert result.changed
    assert not (agent_dir / "models.json").exists()


def test_mcp_server_entry_points_at_the_server_module():
    entry = mcp_server_entry("/usr/bin/python3")
    assert entry["envwiki"]["command"] == "/usr/bin/python3"
    assert entry["envwiki"]["args"] == ["-m", "envwiki.mcp_server"]
