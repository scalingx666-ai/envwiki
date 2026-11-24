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
