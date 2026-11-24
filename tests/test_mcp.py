"""Tests for the MCP server surface."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).parents[1] / "src"


def _call(coro_factory):
    return asyncio.run(coro_factory())


def _server_params():
    from mcp import StdioServerParameters

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "envwiki.mcp_server"],
        env=env,
    )


def _run_client(body):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async def main():
        async with stdio_client(_server_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await body(session)

    return _call(main)


def test_server_tells_the_agent_that_it_decides_the_task():
    async def body(session):
        result = await session.initialize()
        return result.instructions or ""

    instructions = _run_client(body)
    assert "stage_source" in instructions
    assert "scaffold_task" in instructions
    assert "It does not decide what the task should be" in instructions


def test_server_exposes_the_recipe_tools():
    async def body(session):
        tools = await session.list_tools()
        return [t.name for t in tools.tools]

    names = _run_client(body)
    assert set(names) >= {
        "list_recipes",
        "get_recipe",
        "search_recipes",
        "recommend_recipes",
        "plan_task",
        "list_recipe_families",
        "stage_source",
        "list_staged",
        "scaffold_task",
        "validate_task",
    }


def test_list_recipes_returns_the_library():
    async def body(session):
        res = await session.call_tool("list_recipes", {})
        return json.loads(res.content[0].text)

    payload = _run_client(body)
    assert payload["count"] >= 25
    assert payload["recipes"][0]["id"]


def test_plan_task_expands_the_best_match():
    async def body(session):
        res = await session.call_tool(
            "plan_task",
            {
                "source_profile": "a python CLI that converts CSV to JSON offline",
                "limit": 2,
            },
        )
        return json.loads(res.content[0].text)

    payload = _run_client(body)
    assert payload["count"] == 2
    top = payload["plan"][0]
    assert top["rank"] == 1
    assert len(top["steps"]) >= 5
    assert top["source_papers"]
    assert "steps" not in payload["plan"][1]


def test_get_recipe_and_unknown_id():
    async def body(session):
        good = await session.call_tool("get_recipe", {"recipe_id": "dockerized-terminal-blueprint"})
        bad = await session.call_tool("get_recipe", {"recipe_id": "does-not-exist"})
        return json.loads(good.content[0].text), json.loads(bad.content[0].text)

    recipe, missing = _run_client(body)
    assert recipe["id"] == "dockerized-terminal-blueprint"
    assert len(recipe["steps"]) >= 5
    assert missing["error"]

VERIFIER_CODE = (
    "#!/bin/bash" + chr(10)
    + "mkdir -p /logs/verifier" + chr(10)
    + "echo 1 > /logs/verifier/reward.txt" + chr(10)
    + "test -f /app/out.txt" + chr(10)
)


def test_stage_source_stages_an_upload(tmp_path):
    upload = tmp_path / "notes.md"
    upload.write_text("material", encoding="utf-8")
    workspace = tmp_path / "stage"

    async def body(session):
        res = await session.call_tool(
            "stage_source",
            {"uploads": [str(upload)], "workspace": str(workspace)},
        )
        return json.loads(res.content[0].text)

    payload = _run_client(body)
    assert payload["staging_dir"].startswith(str(workspace))
    assert payload["sources"]
    assert "uploads/notes.md" in payload["tree"]
    assert "material" in payload["digest"]


def test_scaffold_task_writes_the_task_and_names_the_org(tmp_path):
    staging = tmp_path / "stage"
    staging.mkdir()

    async def body(session):
        res = await session.call_tool(
            "scaffold_task",
            {
                "name": "demo-task",
                "instruction_md": "Do the thing.",
                "verifier_code": VERIFIER_CODE,
                "staging_dir": str(staging),
                "org": "acme",
                "source_notes": "following dockerized-terminal-blueprint",
            },
        )
        return json.loads(res.content[0].text)

    payload = _run_client(body)
    task_dir = Path(payload["task_dir"])
    assert task_dir == staging / "tasks" / "demo-task"
    toml_text = (task_dir / "task.toml").read_text(encoding="utf-8")
    assert 'name = "acme/demo-task"' in toml_text
    assert "dockerized-terminal-blueprint" in payload["recipes"]
    assert "tests/test.sh" in payload["files"]


def test_validate_task_accepts_what_scaffold_task_wrote(tmp_path):
    staging = tmp_path / "stage"
    staging.mkdir()

    async def body(session):
        made = await session.call_tool(
            "scaffold_task",
            {
                "name": "demo-task",
                "instruction_md": "Do the thing.",
                "verifier_code": VERIFIER_CODE,
                "staging_dir": str(staging),
            },
        )
        task_dir = json.loads(made.content[0].text)["task_dir"]
        checked = await session.call_tool("validate_task", {"task_dir": task_dir})
        return json.loads(checked.content[0].text)

    payload = _run_client(body)
    assert payload["ok"] is True
    assert payload["errors"] == []


def test_validate_task_reports_a_broken_task(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()

    async def body(session):
        res = await session.call_tool("validate_task", {"task_dir": str(task_dir)})
        return json.loads(res.content[0].text)

    payload = _run_client(body)
    assert payload["ok"] is False
    assert payload["errors"]

