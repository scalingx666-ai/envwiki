"""Loading, searching and matching the recipe library."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from envwiki.recipes import vector_index
from envwiki.recipes.schema import Recipe
from envwiki.recipes.text import tokenize

DATA_DIR = Path(__file__).resolve().parent / "data" / "families"
DATA_PATH = Path(__file__).resolve().parent / "data" / "recipes.json"

#: The words a source profile uses for each kind of material.
#:
#: The facet is what makes two recipes comparable, so a profile has to be
#: able to name one without knowing the library's vocabulary. "a python
#: repository" has to reach the code facet without saying "code".
#: How much of the score each source carries.
LEXICAL_WEIGHT = 0.55
VECTOR_WEIGHT = 0.45
#: The weight of the tier. It has to outweigh both of the others: the
#: structured fields decide the order, the prose only orders within it.
TIER_WEIGHT = 2.0

MATERIAL_ALIASES: dict[str, set[str]] = {
    "code": {
        "code", "repository", "repo", "program", "script", "library",
        "package", "function", "python", "rust", "javascript", "typescript",
        "golang", "source", "cli",
    },
    "web": {
        "web", "website", "site", "page", "html", "css", "frontend",
        "browser", "dom", "url", "playwright",
    },
    "gui": {
        "gui", "desktop", "window", "click", "button", "screenshot",
        "mouse", "keyboard", "widget",
    },
    "api": {
        "api", "service", "endpoint", "rest", "graphql", "tool", "mcp",
        "http", "rpc",
    },
    "data": {
        "data", "dataset", "csv", "records", "table", "rows", "columns",
        "etl", "pipeline", "spreadsheet",
    },
    "simulation": {
        "simulation", "simulator", "world", "physics", "dynamics",
    },
    "multi-agent": {
        "multi-agent", "multiagent", "collaboration", "cooperation", "game",
        "negotiation", "partners",
    },
    "embodied": {
        "embodied", "robot", "physical", "spatial", "navigation", "vehicle",
    },
    "trajectory": {
        "trajectory", "trajectories", "trace", "traces", "logs", "history",
        "session",
    },
    "specification": {
        "spec", "specification", "specs", "requirements", "interface",
        "contract", "api-docs",
    },
    "infrastructure": {
        "infrastructure", "sandbox", "platform", "harness", "container",
        "docker", "compose",
    },
    "paper": {
        "paper", "papers", "article", "preprint", "arxiv", "abstract",
        "manuscript", "study", "research", "prose", "document",
    },
}

#: Words that say a method needs a runtime the material does not have.
#: A profile naming one of these, without also naming something that
#: supplies it, is asking for a method the material cannot support.
RUNTIME_NEEDS = (
    "runnable", "executable", "checkout", "entry", "build",
    "installable", "resettable", "replayable",
)


def _tokens(text: str) -> list[str]:
    return tokenize(text)


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
            out.append(self.card(recipe))
        return out

    # -- the card ------------------------------------------------------
    def card(self, recipe: Recipe) -> dict:
        """What an agent compares: fields, not prose.

        The card is deliberately made of fields and one line. Two methods
        are compared by what they work on, what they pose, what they need
        and what they produce; the prose about when to use them, and the
        papers behind them, are one get_recipe call away.
        """
        return {
            "id": recipe.id,
            "name": recipe.name,
            "family": recipe.family,
            "role": recipe.role,
            "material_kind": list(recipe.material_kind),
            "task_kind": recipe.task_kind,
            "needs": list(recipe.needs),
            "produces": recipe.produces,
            "effort": recipe.effort,
            "summary": recipe.summary,
        }

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
        score += self._facet_bonus(recipe, wanted)
        return score

    def _facet_bonus(self, recipe: Recipe, wanted: set[str]) -> float:
        """How well the recipe's structured fields fit the source profile.

        The fields are what make two recipes comparable: the kind of
        material the method works on, the kind of gap it poses, and the
        role it plays. A profile that names one of them is asking for a
        recipe with that field, so the match is worth more than a
        coincidental common word.
        """
        bonus = 0.0
        for kind in recipe.material_kind:
            aliases = MATERIAL_ALIASES.get(kind, {kind})
            if aliases & wanted:
                bonus += 1.8
        if recipe.task_kind in wanted:
            bonus += 0.8
        if recipe.role in wanted:
            bonus += 0.6
        elif recipe.role == "create":
            # An agent asking for a method wants one that makes a task.
            # A method that only curates a set of them is a step later,
            # not the answer to this question.
            bonus += 0.5
        for need in recipe.needs:
            tokens = set(_tokens(need))
            if tokens and len(tokens & wanted) >= max(1, len(tokens) - 1):
                bonus += 0.25
        return bonus

    def _tier(self, recipe: Recipe, wanted: set[str]) -> int:
        """How directly the structured fields answer the profile.

        2 - the profile names the kind of material the method works on.
        1 - the profile names the kind of gap, the role, or a need.
        0 - the profile names none of them.

        The tier decides the order before any prose is read: a profile
        that says it has a repository wants a method that works on
        repositories, whatever the words happen to overlap with.

        A paper-only profile is the exception. A paper is prose: it has
        no runtime, so a method that needs a runnable checkout cannot
        work on it. Those methods are demoted instead of ranked first.
        """
        paper_profile = bool(MATERIAL_ALIASES["paper"] & wanted)
        needs_runtime = any(
            set(_tokens(need)) & set(RUNTIME_NEEDS) for need in recipe.needs
        )
        for kind in recipe.material_kind:
            if MATERIAL_ALIASES.get(kind, {kind}) & wanted:
                if (
                    paper_profile
                    and needs_runtime
                    and kind in {"code", "web", "gui", "infrastructure"}
                ):
                    continue
                return 2
        if recipe.task_kind in wanted or recipe.role in wanted:
            return 1
        for need in recipe.needs:
            tokens = set(_tokens(need))
            if tokens and len(tokens & wanted) >= max(1, len(tokens) - 1):
                return 1
        return 0

    def _lexical(self, query: str, wanted: set[str]) -> list[tuple[Recipe, float]]:
        """The word-overlap ranking, with the signal phrases on top."""
        if not wanted:
            return []
        scored = [(r, self._score(r, wanted)) for r in self.recipes]
        scored = [item for item in scored if item[1] > 0]
        scored.sort(key=lambda item: (-item[1], item[0].id))
        return scored

    def _vector(self, query: str, limit: int) -> list[tuple[Recipe, float]]:
        """The vector ranking, when the vector store is there."""
        hits = vector_index.search(self.recipes, query, limit=limit)
        if hits is None:
            return []
        return [
            (self._by_id[recipe_id], score)
            for recipe_id, score in hits
            if recipe_id in self._by_id and score > 0
        ]

    def search(self, query: str, limit: int = 6) -> list[tuple[Recipe, float]]:
        """Rank recipes by how well they match the query.

        Three pieces of evidence, in this order of authority:

        1. the structured fields: the kind of material, the kind of gap,
           the role. A profile that names one of them is asking for a
           recipe with that field, so the match sets the tier and the
           tier sets the order.
        2. the index: two full text scores, over what the recipe says
           it is for and over the whole recipe.
        3. the words the recipe author wrote down, in the signal phrases
           of when_to_use.

        The same question always gets the same answer: every score is
        exact, and what is left over is broken by name.
        """
        wanted = set(_tokens(query))
        lexical = self._lexical(query, wanted)
        vector = self._vector(query, len(self.recipes))

        best_lexical = max((score for _, score in lexical), default=0.0)
        lexical_scores = {
            recipe.id: (score / best_lexical if best_lexical else 0.0)
            for recipe, score in lexical
        }
        vector_scores = {recipe.id: score for recipe, score in vector}

        ranked: list[tuple[Recipe, float]] = []
        for recipe in self.recipes:
            blend = (
                LEXICAL_WEIGHT * lexical_scores.get(recipe.id, 0.0)
                + VECTOR_WEIGHT * vector_scores.get(recipe.id, 0.0)
            )
            tier = self._tier(recipe, wanted)
            ranked.append((recipe, TIER_WEIGHT * tier + blend))
        ranked.sort(key=lambda item: (-item[1], item[0].id))
        if not ranked or ranked[0][1] <= 0:
            return []
        best = ranked[0][1]
        return [(recipe, score / best) for recipe, score in ranked[:limit]]

    def engine(self) -> str:
        """Which engine is ranking the recipes right now."""
        return vector_index.engine()

    def recommend(self, source_profile: str, limit: int = 5) -> list[tuple[Recipe, float]]:
        """Rank recipes by how well they fit a description of the source."""
        return self.search(source_profile, limit=limit)

    def plan(self, source_profile: str, limit: int = 3) -> list[dict]:
        """Candidate methods, with the full procedure of the best one.

        A harness can act on this in one round trip: it gets the ranked
        alternatives and, for the top one, the steps to follow.

        The alternatives stay small on purpose. They are cards, so the
        agent compares them by their fields; the long prose of a method it
        did not pick is one get_recipe call away, and reading it costs
        more than choosing wrongly would.
        """
        hits = self.recommend(source_profile, limit=limit)
        out: list[dict] = []
        for rank, (recipe, score) in enumerate(hits, 1):
            entry = self.card(recipe)
            entry["rank"] = rank
            entry["match_score"] = round(score, 4)
            if rank == 1:
                # The procedure of the top match, and what it needs to run.
                # The papers behind it and the notes about curating a set
                # are in get_recipe: neither is needed to follow a method.
                entry["steps"] = [step.model_dump() for step in recipe.steps]
                entry["inputs"] = list(recipe.inputs)
                entry["verifier"] = list(recipe.verifier)
                entry["pitfalls"] = list(recipe.pitfalls)
                entry["when_to_use"] = list(recipe.when_to_use)
                entry["not_when_to_use"] = list(recipe.not_when_to_use)
                # The papers behind the method, as ids and titles. They say
                # where the method comes from, which is worth carrying, but
                # the notes on each paper are not.
                entry["source_papers"] = [
                    {"arxiv_id": p.arxiv_id, "title": p.title}
                    for p in recipe.source_papers
                ]
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
