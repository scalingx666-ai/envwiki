"""Fallback harness: the model talks to the endpoint directly.

It has no filesystem tools, but it does have the envwiki toolbox: the same
tools the MCP server exposes, called in process. The contract therefore
stays in one place, and a task built this way is built exactly like a task
built by an agent that speaks MCP over the wire.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from envwiki.harness.base import Harness, HarnessResult
from envwiki.llm.client import LLMClient, image_data_url
from envwiki.toolbox import call_tool_async, tool_definitions

#: How many tool rounds the model may take before envwiki gives up.
MAX_ROUNDS = 12


def _arguments(call: dict[str, Any]) -> dict[str, Any]:
    """The arguments of one tool call, decoded."""
    function = call.get("function") or {}
    raw = function.get("arguments") or call.get("arguments") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


class DirectHarness(Harness):
    """Calls the model directly and hands it the envwiki tools."""

    name = "direct"

    def __init__(self, config, *, max_rounds: int = MAX_ROUNDS) -> None:
        super().__init__(config)
        self.max_rounds = max_rounds

    def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        images: list[Path] | None = None,
        timeout: float = 900.0,
        system_prompt: str | None = None,
    ) -> HarnessResult:
        client = LLMClient(self.config.endpoint, timeout=timeout)
        return asyncio.run(self._run(client, prompt, cwd, images, system_prompt))

    async def _run(
        self,
        client: LLMClient,
        prompt: str,
        cwd: Path,
        images: list[Path] | None,
        system_prompt: str | None,
    ) -> HarnessResult:
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if images:
            parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            parts += [
                {"type": "image_url", "image_url": {"url": image_data_url(path)}}
                for path in images
            ]
            messages.append({"role": "user", "content": parts})
        else:
            messages.append({"role": "user", "content": prompt})

        tools = await tool_definitions()
        for _ in range(self.max_rounds):
            result = client.chat(messages, tools=tools)
            if not result.ok:
                return HarnessResult("", False, result.error)
            if not result.tool_calls:
                return HarnessResult(result.text, True, raw_output=result.text)

            messages.append(
                {
                    "role": "assistant",
                    "content": result.text or "",
                    "tool_calls": result.tool_calls,
                }
            )
            for call in result.tool_calls:
                name = str((call.get("function") or {}).get("name") or "")
                arguments = _arguments(call)
                if name == "scaffold_task" and not arguments.get("staging_dir"):
                    # The workspace is where the task must land; the model
                    # does not have to repeat it.
                    arguments["staging_dir"] = str(cwd)
                payload = await call_tool_async(name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(call.get("id") or ""),
                        "content": json.dumps(payload, ensure_ascii=False),
                    }
                )

        return HarnessResult(
            "",
            False,
            "the model kept calling tools for " + str(self.max_rounds) + " rounds",
        )
