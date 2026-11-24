"""Fallback harness: call the model directly, with no agent tooling."""

from __future__ import annotations

from pathlib import Path

from envwiki.harness.base import Harness, HarnessResult
from envwiki.llm.client import LLMClient


class DirectHarness(Harness):
    """Sends the prompt (and any images) straight to the chat endpoint."""

    name = "direct"

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
        if images:
            result = client.chat_with_images(prompt, images, system=system_prompt)
        else:
            messages: list[dict] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            result = client.chat(messages)
        if not result.ok:
            return HarnessResult("", False, result.error)
        return HarnessResult(result.text, True, raw_output=str(result.raw or ""))
