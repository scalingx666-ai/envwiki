#"""Minimal OpenAI-compatible chat client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from envwiki.config import ModelEndpoint


@dataclass(slots=True)
class ChatResult:
    text: str
    ok: bool
    error: str = ""
    raw: dict[str, Any] | None = None


def image_data_url(path: Path) -> str:
    """Encode a local image as a data URL for vision models."""
    import base64
    import mimetypes

    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class LLMClient:
    """Talks to an OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, endpoint: ModelEndpoint, timeout: float = 300.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def list_models(self) -> list[str]:
        try:
            resp = httpx.get(
                self.endpoint.models_url,
                headers=self.endpoint.auth_headers(),
                timeout=30.0,
            )
            resp.raise_for_status()
            payload = resp.json()
            return [m.get("id", "") for m in payload.get("data", []) if m.get("id")]
        except Exception:
            return []

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ChatResult:
        body: dict[str, Any] = {
            "model": self.endpoint.model,
            "messages": messages,
            "stream": False,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if extra:
            body.update(extra)

        try:
            resp = httpx.post(
                self.endpoint.chat_url,
                headers={**self.endpoint.auth_headers(), "Content-Type": "application/json"},
                json=body,
                timeout=self.timeout,
            )
        except Exception as exc:
            return ChatResult("", False, f"{type(exc).__name__}: {exc}")

        if resp.status_code >= 400:
            return ChatResult("", False, f"HTTP {resp.status_code}: {resp.text[:400]}")

        try:
            payload = resp.json()
        except json.JSONDecodeError:
            return ChatResult("", False, f"non-JSON response: {resp.text[:200]}")

        choices = payload.get("choices") or []
        if not choices:
            return ChatResult("", False, f"no choices in response: {str(payload)[:300]}")
        message = choices[0].get("message") or {}
        text = (message.get("content") or "").strip()
        if not text and message.get("reasoning_content"):
            text = str(message["reasoning_content"]).strip()
        return ChatResult(text, True, raw=payload)

    def chat_with_images(
        self,
        prompt: str,
        images: list[Path],
        system: str | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Send a prompt plus local images as vision content parts."""
        parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            parts.append({"type": "image_url", "image_url": {"url": image_data_url(img)}})

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": parts})
        return self.chat(messages, **kwargs)
