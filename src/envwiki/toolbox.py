"""In-process access to the envwiki MCP toolbox.

The MCP server is the one place where the tool contract lives. This module
exposes the very same tools to a plain chat client, so the fallback harness
speaks the same contract as an agent that talks MCP over the wire: one
contract, two transports.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from envwiki.mcp_server import server


async def tool_definitions() -> list[dict[str, Any]]:
    """Every tool of the MCP server, as OpenAI-style function definitions."""
    tools = await server.list_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


async def call_tool_async(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one MCP tool in this process and return its payload."""
    try:
        result = await server.call_tool(name, dict(arguments or {}))
    except Exception as exc:
        return {"error": str(exc)}
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
        return payload if isinstance(payload, dict) else {"result": payload}
    return {"error": "tool " + name + " returned nothing"}


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one MCP tool in this process, outside a running event loop."""
    return asyncio.run(call_tool_async(name, arguments))
