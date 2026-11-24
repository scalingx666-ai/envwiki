"""Loading, searching and matching the recipe library."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from envwiki.recipes.schema import Recipe

DATA_DIR = Path(__file__).resolve().parent / "data" / "families"
DATA_PATH = Path(__file__).resolve().parent / "data" / "recipes.json"

_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{1,}")

_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "are", "was",
    "using", "use", "used", "via", "its", "not", "can", "all", "any", "one",
    "task", "tasks", "agent", "agents", "env", "environment", "environments",
    "paper", "papers", "method", "methods", "based",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS]


class RecipeLibrary:
    """The set of recipes, with search and recommendation helpers."""

    def __init__(self, recipes: list[Recipe]) -> None:
        self.recipes = recipes
        self._by_id = {r.id: r for r in recipes}
        self._index = {r.id: _tokens(r.searchable_text()) for r in recipes}
        self._signals = {
            r.id: [_tokens(phrase) for phrase in r.when_to_use] for r in recipes
        }

    # -- lookup --------------------------------------------------------
    def get(self, recipe_id: str) -> Recipe | None:
        return self._by_id.get((recipe_id or "").strip().lower())

    def families(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for recipe in self.recipes:
            counts[recipe.family] = counts.get(recipe.family, 0) + 1
        return dict(sorted(counts.items()))

    def summaries(self, family: str = "", effort: str = "") -> list[dict]:
        out = []
        for recipe in self.recipes:
            if family and recipe.family != family:
                continue
            if effort and recipe.effort != effort:
                continue
            out.append(
                {
                    "id": recipe.id,
                    "name": recipe.name,
                    "family": recipe.family,
                    "effort": recipe.effort,
                    "summary": recipe.summary,
                    "when_to_use": recipe.when_to_use,
                    "source_papers": [
                        {"arxiv_id": p.arxiv_id, "title": p.title} for p in recipe.source_papers
                    ],
                }
            )
        return out

    # -- scoring -------------------------------------------------------
    def _score(self, recipe: Recipe, wanted: set[str]) -> float:
        """Overlap with the recipe body, plus a bonus for matching signals.

        A signal phrase from when_to_use counts when most of its words appear
        in the source profile: that is a much stronger hint than one common
        word anywhere in the recipe.
        """
        tokens = set(self._index[recipe.id])
        overlap = len(wanted & tokens)
        score = overlap / (len(wanted) ** 0.5) if wanted else 0.0
        for phrase in self._signals[recipe.id]:
            if not phrase:
                continue
            hits = sum(1 for token in phrase if token in wanted)
            if hits >= max(2, int(len(phrase) * 0.6)):
                score += 1.5
        if recipe.family.lower() in wanted:
            score += 0.5
        return score

    def search(self, query: str, limit: int = 6) -> list[tuple[Recipe, float]]:
        """Rank recipes by how well they match the query."""
        wanted = set(_tokens(query))
        if not wanted:
            return []
        scored = [(r, self._score(r, wanted)) for r in self.recipes]
        scored = [item for item in scored if item[1] > 0]
        scored.sort(key=lambda item: (-item[1], item[0].id))
        return scored[:limit]

    def recommend(self, source_profile: str, limit: int = 5) -> list[tuple[Recipe, float]]:
        """Rank recipes by how well they fit a description of the source."""
        return self.search(source_profile, limit=limit)

    def plan(self, source_profile: str, limit: int = 3) -> list[dict]:
        """Candidate methods with the full procedure of the best one.

        A harness can act on this in one round trip: it gets the ranked
        alternatives and, for the top one, the steps to follow.
        """
        hits = self.recommend(source_profile, limit=limit)
        out: list[dict] = []
        for rank, (recipe, score) in enumerate(hits, 1):
            entry = {
                "rank": rank,
                "id": recipe.id,
                "name": recipe.name,
                "family": recipe.family,
                "match_score": round(score, 4),
                "summary": recipe.summary,
                "when_to_use": recipe.when_to_use,
                "not_when_to_use": recipe.not_when_to_use,
                "inputs": recipe.inputs,
                "verifier": recipe.verifier,
                "pitfalls": recipe.pitfalls,
                "effort": recipe.effort,
                "source_papers": [
                    {"arxiv_id": p.arxiv_id, "title": p.title, "note": p.note}
                    for p in recipe.source_papers
                ],
            }
            if rank == 1:
                entry["steps"] = [step.model_dump() for step in recipe.steps]
            out.append(entry)
        return out


@lru_cache(maxsize=1)
def load_library(path: str | None = None) -> RecipeLibrary:
    """Load the recipe library.

    Recipes live in one JSON file per family under data/families/, so the
    library can grow and be reviewed family by family.
    """
    if path:
        target = Path(path)
        files = [target] if target.is_file() else sorted(target.glob("*.json"))
    else:
        files = sorted(DATA_DIR.glob("*.json")) if DATA_DIR.is_dir() else []
        if not files and DATA_PATH.exists():
            files = [DATA_PATH]

    recipes: list[Recipe] = []
    for file in files:
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = raw.get("recipes", raw if isinstance(raw, list) else [])
        for item in items:
            recipes.append(Recipe.model_validate(item))
    recipes.sort(key=lambda r: (r.family, r.id))
    return RecipeLibrary(recipes)
