"""Tests for the in-process toolbox."""

from __future__ import annotations

import asyncio

from envwiki.toolbox import call_tool, tool_definitions


def test_toolbox_lists_the_same_tools_as_the_server():
    specs = asyncio.run(tool_definitions())
    names = {spec["function"]["name"] for spec in specs}
    assert {
        "list_recipes",
        "get_recipe",
        "plan_task",
        "stage_source",
        "list_staged",
        "scaffold_task",
        "validate_task",
    } <= names
    for spec in specs:
        assert spec["function"]["parameters"]["type"] == "object"


def test_call_tool_runs_a_tool_in_process():
    payload = call_tool("list_recipe_families", {})
    assert payload["total_recipes"] >= 25
    assert payload["families"]


def test_call_tool_reports_an_unknown_tool():
    payload = call_tool("does_not_exist", {})
    assert "error" in payload
