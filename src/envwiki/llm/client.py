"""A minimal client for the OpenAI-compatible endpoint.

envwiki itself never calls a model: the agent does that, through the MCP
server. This client exists so the CLI can ask the endpoint what it serves.
"""

from __future__ import annotations

import httpx

from envwiki.config import ModelEndpoint


class LLMClient:
    """Reaches an OpenAI-compatible endpoint."""

    def __init__(self, endpoint: ModelEndpoint, timeout: float = 30.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def list_models(self) -> list[str]:
        """The model ids the endpoint serves, or an empty list."""
        try:
            resp = httpx.get(
                self.endpoint.models_url,
                headers=self.endpoint.auth_headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            return [m.get("id", "") for m in payload.get("data", []) if m.get("id")]
        except Exception:
            return []
