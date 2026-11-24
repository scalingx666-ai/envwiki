"""Runtime configuration for envwiki.

All knobs are environment-driven so the tool can run unattended.

    ENVWIKI_BASE_URL   OpenAI-compatible base URL   (default http://127.0.0.1:8787/v1)
    ENVWIKI_API_KEY    API key for that endpoint    (default sk-my-secret)
    ENVWIKI_MODEL      Model id                     (default hy4flash-free)
    ENVWIKI_PROVIDER   Provider name written into pi's models.json
    ENVWIKI_HARNESS    Harness backend: pi | direct (default pi)
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
    """An OpenAI-compatible chat-completions endpoint."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    provider: str = DEFAULT_PROVIDER
    context_window: int = 128_000
    max_tokens: int = 8_192
    supports_images: bool = True
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
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/models"

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


@dataclass(slots=True)
class EnvwikiConfig:
    """Everything a build run needs."""

    endpoint: ModelEndpoint = field(default_factory=ModelEndpoint.from_env)
    harness: str = "pi"
    #: Where staged sources live while the harness explores them.
    workspace: Path = field(default_factory=lambda: Path.cwd() / ".envwiki-workspace")
    #: Hard cap on characters of source material handed to the model.
    max_context_chars: int = 120_000
    #: Pi binary; resolved from PATH when None.
    pi_bin: str | None = None
    agent_dir: Path = field(default_factory=lambda: Path.home() / ".pi" / "agent")

    def harness_env(self) -> dict[str, str]:
        """Extra environment for the harness subprocess."""
        env = dict(os.environ)
        env[self.endpoint.api_key_env_var] = self.endpoint.api_key
        return env
