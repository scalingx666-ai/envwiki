"""The paper corpus the recipe library is grounded in.

Every recipe cites arXiv ids; this index is what makes those citations
checkable without trusting the author of the recipe.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CORPUS_PATH = Path(__file__).resolve().parent / "data" / "corpus.json"


@lru_cache(maxsize=1)
def load_corpus() -> dict[str, dict]:
    """Map arXiv id to the paper's title, family and source section."""
    if not CORPUS_PATH.exists():
        return {}
    raw = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return dict(raw.get("papers", {}))


def is_grounded(arxiv_id: str) -> bool:
    """True when the id belongs to the corpus the library was built from."""
    return (arxiv_id or "").strip().lower() in load_corpus()


def corpus_size() -> int:
    return len(load_corpus())
