"""Runtime configuration for envwiki.

The knobs are environment-driven so the tool can run unattended.

    ENVWIKI_BASE_URL   OpenAI-compatible base URL   (default http://127.0.0.1:8787/v1)
    ENVWIKI_API_KEY    API key for that endpoint    (default sk-my-secret)
    ENVWIKI_MODEL      Model id                     (default hy4flash-free)
    ENVWIKI_PROVIDER   Provider name written into pi's models.json
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "http://127.0.0.1:8787/v1"
DEFAULT_API_KEY = "sk-my-secret"
DEFAULT_MODEL = "hy4flash-free"
DEFAULT_PROVIDER = "envwiki-local"


@dataclass(slots=True)
class ModelEndpoint:
    """An OpenAI-compatible endpoint an agent can talk to."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    provider: str = DEFAULT_PROVIDER
    context_window: int = 128_000
    max_tokens: int = 8_192
    #: envwiki writes "$ENVWIKI_API_KEY" into pi's models.json and exports the
    #: real value at runtime, so the secret never lands in a config file.
    api_key_env_var: str = "ENVWIKI_API_KEY"

    @classmethod
    def from_env(cls, **overrides: object) -> ModelEndpoint:
        env = {
            "base_url": os.environ.get("ENVWIKI_BASE_URL", DEFAULT_BASE_URL),
            "api_key": os.environ.get("ENVWIKI_API_KEY", DEFAULT_API_KEY),
            "model": os.environ.get("ENVWIKI_MODEL", DEFAULT_MODEL),
            "provider": os.environ.get("ENVWIKI_PROVIDER", DEFAULT_PROVIDER),
        }
        env.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**env)  # type: ignore[arg-type]

    @property
    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/models"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


@dataclass(slots=True)
class EnvwikiConfig:
    """Where envwiki keeps its own configuration."""

    endpoint: ModelEndpoint = field(default_factory=ModelEndpoint.from_env)
    #: Where pi keeps models.json.
    agent_dir: Path = field(default_factory=lambda: Path.home() / ".pi" / "agent")
