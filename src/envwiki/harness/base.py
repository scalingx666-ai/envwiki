"""Harness abstraction: a pluggable agent that turns material into a task spec."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from envwiki.config import EnvwikiConfig


@dataclass(slots=True)
class HarnessResult:
    """What the harness produced."""

    text: str
    ok: bool
    error: str = ""
    raw_output: str = ""
    images: list[Path] = field(default_factory=list)


class Harness(ABC):
    """Base class for agent harnesses.

    A harness receives a prompt plus a working directory that holds the staged
    source material, and returns the model's final text.
    """

    name: str = "harness"

    def __init__(self, config: EnvwikiConfig) -> None:
        self.config = config

    @abstractmethod
    def run(
        self,
        prompt: str,
        *,
        cwd: Path,
        images: list[Path] | None = None,
        timeout: float = 900.0,
        system_prompt: str | None = None,
    ) -> HarnessResult:
        """Execute the prompt and return the assistant's final text."""

    def prepare(self, cwd: Path) -> None:
        """Hook for harness-specific setup inside the staging directory."""
        return None
