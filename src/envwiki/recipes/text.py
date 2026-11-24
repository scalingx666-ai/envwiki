"""Text handling shared by every recipe matcher."""

from __future__ import annotations

import re

#: A term is a lowercase word, possibly with hyphens.
TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{1,}")

#: Words that carry no signal about which method fits.
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "are", "was",
    "using", "use", "used", "via", "its", "not", "can", "all", "any", "one",
    "task", "tasks", "agent", "agents", "env", "environment", "environments",
    "paper", "papers", "method", "methods", "based",
}


def tokenize(text: str) -> list[str]:
    """The terms of a text, without the words that carry no signal."""
    return [term for term in TOKEN_RE.findall((text or "").lower()) if term not in STOPWORDS]
