"""Wiring envwiki into a pi agent.

pi keeps its provider list in models.json and its MCP servers in mcp.json.
envwiki writes an entry for the endpoint you point it at, and never the
secret itself.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from envwiki.config import ModelEndpoint

NL = chr(10)


@dataclass(slots=True)
class RegistrationResult:
    changed: bool
    message: str
    path: str = ""


def _provider_entry(endpoint: ModelEndpoint) -> dict[str, Any]:
    return {
        "name": endpoint.provider,
        "api": "openai-completions",
        "baseUrl": endpoint.base_url,
        "apiKey": "$" + endpoint.api_key_env_var,
        "models": [
            {
                "id": endpoint.model,
                "name": endpoint.model,
                "api": "openai-completions",
                "reasoning": False,
                "input": ["text", "image"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": endpoint.context_window,
                "maxTokens": endpoint.max_tokens,
            }
        ],
    }


def register_provider(
    agent_dir: Path, endpoint: ModelEndpoint, *, dry_run: bool = False
) -> RegistrationResult:
    """Add (or refresh) the endpoint inside pi's models.json.

    The API key is written as an environment reference so the secret never
    lands in a config file.
    """
    path = agent_dir / "models.json"
    data: dict[str, Any] = {"providers": {}}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"providers": {}}

    providers = data.setdefault("providers", {})
    desired = _provider_entry(endpoint)
    if providers.get(endpoint.provider) == desired:
        return RegistrationResult(
            False, "provider '" + endpoint.provider + "' already registered", str(path)
        )

    if dry_run:
        return RegistrationResult(
            True, "would register '" + endpoint.provider + "'", str(path)
        )

    providers[endpoint.provider] = desired
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + NL, encoding="utf-8")
    return RegistrationResult(True, "registered provider '" + endpoint.provider + "'", str(path))


def mcp_server_entry(python_executable: str | None = None) -> dict[str, Any]:
    """The MCP server entry an agent needs to reach envwiki."""
    return {
        "envwiki": {
            "command": python_executable or sys.executable,
            "args": ["-m", "envwiki.mcp_server"],
            "description": (
                "Environment and task synthesis recipes distilled from the "
                "literature, plus the tools that stage material, write a "
                "Harbor task and check it."
            ),
        }
    }
