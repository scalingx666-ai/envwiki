"""Tests for the harness layer."""

from __future__ import annotations

import json
from pathlib import Path

from envwiki.config import EnvwikiConfig, ModelEndpoint
from envwiki.harness.pi_harness import (
    PiHarness,
    build_mcp_config,
    register_provider,
)
from envwiki.llm.client import ChatResult
from envwiki.skills import builtin_skill_dirs


def _config(tmp_path: Path) -> EnvwikiConfig:
    return EnvwikiConfig(
        endpoint=ModelEndpoint.from_env(),
        workspace=tmp_path / "workspace",
        agent_dir=tmp_path / "agent",
    )


def test_prepare_writes_mcp_and_skills(tmp_path: Path):
    harness = PiHarness(_config(tmp_path))
    staging = tmp_path / "staging"
    staging.mkdir()

    harness.prepare(staging)

    mcp = json.loads((staging / ".pi" / "mcp.json").read_text(encoding="utf-8"))
    assert "jina-reader" in mcp["mcpServers"]
    assert "envwiki" in mcp["mcpServers"]
    assert mcp["mcpServers"]["envwiki"]["args"] == ["-m", "envwiki.mcp_server"]
    assert (staging / ".pi" / "skills" / "env-synthesis" / "SKILL.md").is_file()


def test_prepare_can_skip_skills_and_mcp(tmp_path: Path):
    harness = PiHarness(_config(tmp_path))
    staging = tmp_path / "staging"
    staging.mkdir()

    harness.prepare(
        staging, enable_skills=False, enable_jina=False, enable_envwiki=False
    )

    mcp = json.loads((staging / ".pi" / "mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"] == {}
    assert not (staging / ".pi" / "skills").exists()


def test_prepare_accepts_extra_skill_dir(tmp_path: Path):
    extra = tmp_path / "my-skill"
    extra.mkdir()
    frontmatter = chr(10).join(
        ["---", "name: my-skill", "description: x", "---", ""]
    )
    (extra / "SKILL.md").write_text(frontmatter, encoding="utf-8")

    harness = PiHarness(_config(tmp_path))
    staging = tmp_path / "staging"
    staging.mkdir()

    harness.prepare(staging, extra_skill_dirs=[extra])

    assert (staging / ".pi" / "skills" / "my-skill" / "SKILL.md").is_file()


def test_builtin_skill_has_valid_frontmatter():
    dirs = builtin_skill_dirs()
    assert dirs
    for directory in dirs:
        body = (directory / "SKILL.md").read_text(encoding="utf-8")
        head = body.split("---")[1]
        assert "name:" in head
        assert "description:" in head


def test_envwiki_skill_points_at_the_recipe_server():
    skill = (
        Path(__file__).parents[1]
        / "src"
        / "envwiki"
        / "skills"
        / "env-synthesis"
        / "SKILL.md"
    )
    body = skill.read_text(encoding="utf-8")
    assert "plan_task" in body
    assert "get_recipe" in body
    assert "search_recipes" in body
    assert "scaffold_task" in body
    assert "validate_task" in body
    assert "/logs/verifier/reward.txt" in body


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


def test_mcp_config_can_enable_docling():
    config = build_mcp_config(enable_jina=True, enable_docling=True)
    assert config["mcpServers"]["docling"]["command"] == "uvx"
    assert config["mcpServers"]["docling"]["args"] == ["docling-mcp"]

def test_direct_harness_calls_the_envwiki_tools(tmp_path, monkeypatch):
    from envwiki.harness import direct

    seen: list[list[dict]] = []
    offered: list[list[dict]] = []

    class FakeClient:
        def __init__(self, endpoint, timeout=300.0):
            self.endpoint = endpoint

        def chat(self, messages, **kwargs):
            seen.append(messages)
            offered.append(kwargs.get("tools") or [])
            if len(seen) == 1:
                return ChatResult(
                    "",
                    True,
                    tool_calls=[
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "list_recipe_families",
                                "arguments": "{}",
                            },
                        }
                    ],
                )
            return ChatResult("the recipe library is open", True)

    monkeypatch.setattr(direct, "LLMClient", FakeClient)

    harness = direct.DirectHarness(EnvwikiConfig(endpoint=ModelEndpoint.from_env()))
    result = harness.run("go", cwd=tmp_path)

    assert result.ok
    assert result.text == "the recipe library is open"

    # The model was offered the very tools the MCP server exposes.
    tool_names = {spec["function"]["name"] for spec in offered[0]}
    assert {"plan_task", "scaffold_task", "validate_task"} <= tool_names

    # The tool result went back to the model.
    tool_messages = [m for m in seen[-1] if m.get("role") == "tool"]
    assert tool_messages
    assert "total_recipes" in tool_messages[0]["content"]

