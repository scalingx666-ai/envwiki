"""Retrieval over the recipe library, backed by zvec.

zvec is the index. It holds the text of every recipe as two full text
fields - the signal the recipe gives off, and the whole recipe - and,
when an embedding endpoint is configured, one dense vector per recipe.

The ranking is computed here, in plain Python, out of three pieces of
evidence: the two full text scores, the words the recipe author wrote
down, and the structured fields. Two reasons for not letting the index
rank on its own:

- its sparse vector top-k is approximate. Two processes asking the same
  question get different recipes back, and a recommendation that depends
  on which process answered is not a recommendation.
- the structured fields are what a card is compared by, so they have to
  be able to outrank a coincidental common word.

zvec is an optional dependency. Without it envwiki keeps using the
lexical matcher, and every answer says which engine produced it.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import httpx

from envwiki.recipes.schema import Recipe

try:  # pragma: no cover - the import is what the optional extra buys
    import zvec
    from zvec import FtsIndexParam
    from zvec.model.param import HnswIndexParam
    from zvec.model.param.query import Fts, Query
    from zvec.model.schema import CollectionSchema, FieldSchema, VectorSchema
    from zvec.typing import DataType

    ZVEC_AVAILABLE = True
except Exception:  # pragma: no cover
    ZVEC_AVAILABLE = False

#: Bumped when the layout of the index changes, so an index built by an
#: older version is never reused.
INDEX_VERSION = "2"

#: How much of the score each source carries.
SIGNAL_WEIGHT = 0.45
BODY_WEIGHT = 0.45
DENSE_WEIGHT = 0.10


def signal_text(recipe: Recipe) -> str:
    """What the recipe claims to be for.

    The short summary is the card, but the signal a query matches against
    has to include the longer distillation and the structured fields: a
    summary trimmed to two sentences loses the wording a real source
    profile would use.
    """
    parts = [recipe.summary, recipe.background]
    parts.extend(recipe.material_kind)
    parts.append(recipe.task_kind)
    parts.append(recipe.role)
    parts.extend(recipe.needs)
    parts.append(recipe.produces)
    parts.extend(recipe.when_to_use)
    parts.extend(recipe.not_when_to_use)
    parts.extend(recipe.inputs)
    return chr(10).join(part for part in parts if part)


def detail_text(recipe: Recipe) -> str:
    """The whole recipe: signals plus the procedure."""
    parts = [signal_text(recipe)]
    parts.extend(step.title + " " + step.detail + " " + step.accept for step in recipe.steps)
    parts.extend(recipe.verifier)
    parts.extend(recipe.pitfalls)
    return chr(10).join(part for part in parts if part)


def dense_settings() -> tuple[str, str, str] | None:
    """The embedding endpoint to use for dense vectors, if one is configured."""
    base = os.environ.get("ENVWIKI_EMBEDDING_BASE_URL", "").strip()
    model = os.environ.get("ENVWIKI_EMBEDDING_MODEL", "").strip()
    if not base or not model:
        return None
    key = os.environ.get("ENVWIKI_EMBEDDING_API_KEY", "")
    return base, model, key


def embed(texts: list[str], base: str, model: str, api_key: str) -> list[list[float]]:
    """Embed texts with an OpenAI-compatible embeddings endpoint."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    response = httpx.post(
        base.rstrip("/") + "/embeddings",
        headers=headers,
        json={"model": model, "input": texts},
        timeout=120.0,
    )
    response.raise_for_status()
    payload = response.json()
    return [item["embedding"] for item in payload.get("data", [])]


def fingerprint(recipes: list[Recipe]) -> str:
    """A name for the index of this exact library."""
    digest = hashlib.sha256()
    digest.update(INDEX_VERSION.encode("utf-8"))
    for recipe in sorted(recipes, key=lambda r: r.id):
        digest.update(recipe.id.encode("utf-8"))
        digest.update(recipe.model_dump_json().encode("utf-8"))
    settings = dense_settings()
    if settings:
        digest.update(("|dense|" + settings[0] + "|" + settings[1]).encode("utf-8"))
    return digest.hexdigest()[:16]


def index_path(recipes: list[Recipe]) -> Path:
    """Where the index of this library lives on disk."""
    root = Path(
        os.environ.get("ENVWIKI_INDEX_DIR", str(Path.home() / ".cache" / "envwiki"))
    )
    return root / ("recipes-" + fingerprint(recipes) + ".zvec")


def _schema(with_dense: bool, dimension: int) -> Any:
    """The layout of the collection.

    Two full text fields, one for the signal and one for the whole
    recipe. A dense field only when there is an endpoint to embed with.
    """
    vectors = []
    if with_dense:
        vectors.append(
            VectorSchema(
                "dense",
                DataType.VECTOR_FP32,
                dimension=dimension,
                index_param=HnswIndexParam(),
            )
        )
    return CollectionSchema(
        name="recipes",
        fields=[
            FieldSchema("id", DataType.STRING, nullable=False),
            FieldSchema(
                "body",
                DataType.STRING,
                nullable=False,
                index_param=FtsIndexParam(tokenizer_name="standard", filters=["lowercase"]),
            ),
            FieldSchema(
                "signal",
                DataType.STRING,
                nullable=False,
                index_param=FtsIndexParam(tokenizer_name="standard", filters=["lowercase"]),
            ),
            FieldSchema("family", DataType.STRING, nullable=True),
            FieldSchema("effort", DataType.STRING, nullable=True),
        ],
        vectors=vectors,
    )


def build(recipes: list[Recipe], path: Path | None = None) -> Path:
    """Build the index of the library and return its path."""
    if not ZVEC_AVAILABLE:
        raise RuntimeError("zvec is not installed: pip install 'envwiki[vector]'")

    target = path or index_path(recipes)
    target.parent.mkdir(parents=True, exist_ok=True)

    settings = dense_settings()
    embeddings: list[list[float]] = []
    if settings:
        base, model, api_key = settings
        embeddings = embed([detail_text(recipe) for recipe in recipes], base, model, api_key)

    schema = _schema(bool(embeddings), len(embeddings[0]) if embeddings else 0)

    staging = Path(tempfile.mkdtemp(prefix="envwiki-index-", dir=str(target.parent)))
    collection = zvec.create_and_open(path=str(staging / "recipes"), schema=schema)
    try:
        docs = []
        for position, recipe in enumerate(recipes):
            fields = {
                "id": recipe.id,
                "body": detail_text(recipe),
                "signal": signal_text(recipe),
                "family": recipe.family,
                "effort": recipe.effort,
            }
            if embeddings:
                doc = zvec.Doc(id=recipe.id, fields=fields, vectors={"dense": embeddings[position]})
            else:
                doc = zvec.Doc(id=recipe.id, fields=fields)
            docs.append(doc)
        collection.insert(docs)
        collection.flush()
    finally:
        collection.close()

    if target.exists():
        shutil.rmtree(target)
    os.replace(staging / "recipes", target)
    shutil.rmtree(staging, ignore_errors=True)
    return target


def _full_text_scores(collection: Any, field: str, profile: str, topk: int) -> dict[str, float]:
    """The full text score of every document that mentions the profile."""
    try:
        results = collection.query(
            queries=[Query(field_name=field, fts=Fts(match_string=profile))],
            topk=topk,
        )
    except Exception:
        return {}
    scores = {str(doc.id): float(doc.score) for doc in results}
    best = max(scores.values()) if scores else 0.0
    if not best:
        return {}
    return {recipe_id: score / best for recipe_id, score in scores.items()}


def _dense_scores(collection: Any, profile: str, topk: int) -> dict[str, float]:
    """The semantic score of every document, when an endpoint is configured."""
    settings = dense_settings()
    if not settings:
        return {}
    base, model, api_key = settings
    try:
        vector = embed([profile], base, model, api_key)[0]
        results = collection.query(
            queries=[Query(field_name="dense", vector=vector)],
            topk=topk,
        )
    except Exception:
        return {}
    scores = {str(doc.id): float(doc.score) for doc in results}
    best = max(scores.values()) if scores else 0.0
    if not best:
        return {}
    # The dense search is approximate, so its score is quantised: a near
    # miss cannot reorder recipes that the exact scores put on the same
    # level.
    return {recipe_id: round(score / best, 2) for recipe_id, score in scores.items()}


def search(
    recipes: list[Recipe],
    profile: str,
    limit: int = 6,
) -> list[tuple[str, float]] | None:
    """Rank the recipes by text similarity, or None when there is no index.

    The scores are relative: the best match is 1.0 and the rest are
    scaled to it, so they can be compared with the lexical scores.
    """
    if not ZVEC_AVAILABLE:
        return None

    path = index_path(recipes)
    if not path.exists():
        try:
            build(recipes, path)
        except Exception:
            return None

    try:
        collection = zvec.open(path=str(path))
    except Exception:
        return None

    topk = max(len(recipes), 1)
    scores: dict[str, float] = {}
    try:
        for field, weight in (("signal", SIGNAL_WEIGHT), ("body", BODY_WEIGHT)):
            for recipe_id, value in _full_text_scores(collection, field, profile, topk).items():
                scores[recipe_id] = scores.get(recipe_id, 0.0) + weight * value
        for recipe_id, value in _dense_scores(collection, profile, topk).items():
            scores[recipe_id] = scores.get(recipe_id, 0.0) + DENSE_WEIGHT * value
    finally:
        try:
            collection.close()
        except Exception:
            pass

    if not scores:
        return []
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    best = ranked[0][1] or 1.0
    return [(recipe_id, score / best) for recipe_id, score in ranked[:limit]]


def engine() -> str:
    """Which engine answers a query right now."""
    if not ZVEC_AVAILABLE:
        return "lexical"
    return "zvec-fts+dense" if dense_settings() else "zvec-fts"
