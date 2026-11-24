"""Vector retrieval over the recipe library, backed by zvec.

The lexical matcher in library.py knows about words. This module knows about
vectors. Every recipe is stored twice as a BM25 sparse vector - once over its
signals (what it is for) and once over its whole text - plus a dense vector
when an embedding endpoint is configured. A query is a vector similarity
search over those fields, fused with the full text index by reciprocal rank
fusion.

zvec is an optional dependency. Without it envwiki keeps using the lexical
matcher, and every answer says which engine produced it.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from envwiki.recipes.schema import Recipe
from envwiki.recipes.text import tokenize

#: BM25 term saturation.
K1 = 1.2
#: BM25 length normalisation.
B = 0.75

try:  # pragma: no cover - the import is what the optional extra buys
    import zvec
    from zvec import FtsIndexParam
    from zvec.extension import RrfReRanker
    from zvec.model.param import FlatIndexParam, HnswIndexParam
    from zvec.model.param.query import Fts, Query
    from zvec.model.schema import CollectionSchema, FieldSchema, VectorSchema
    from zvec.typing import DataType

    ZVEC_AVAILABLE = True
except Exception:  # pragma: no cover
    ZVEC_AVAILABLE = False


@dataclass(slots=True)
class Bm25Space:
    """A BM25 space over a small corpus, expressed as sparse vectors.

    A document and a query become sparse vectors over the same vocabulary,
    and their dot product is the BM25 score.
    """

    vocabulary: dict[str, int] = field(default_factory=dict)
    document_frequency: dict[int, int] = field(default_factory=dict)
    document_count: int = 0
    average_length: float = 0.0

    def fit(self, documents: dict[str, list[str]]) -> Bm25Space:
        """Learn the vocabulary and the document statistics."""
        lengths: list[int] = []
        for tokens in documents.values():
            lengths.append(len(tokens))
            for token in set(tokens):
                index = self.vocabulary.setdefault(token, len(self.vocabulary))
                self.document_frequency[index] = self.document_frequency.get(index, 0) + 1
        self.document_count = len(documents)
        self.average_length = (sum(lengths) / len(lengths)) if lengths else 0.0
        return self

    def idf(self, index: int) -> float:
        """How rare a term is, in the Robertson form."""
        frequency = self.document_frequency.get(index, 0)
        if frequency == 0:
            return 0.0
        return math.log(1.0 + (self.document_count - frequency + 0.5) / (frequency + 0.5))

    def document_vector(self, tokens: list[str]) -> dict[int, float]:
        """The BM25 weight of every term of a document."""
        counts: dict[int, int] = {}
        for token in tokens:
            index = self.vocabulary.get(token)
            if index is not None:
                counts[index] = counts.get(index, 0) + 1
        length = len(tokens) or 1
        average = self.average_length or 1.0
        normaliser = K1 * (1.0 - B + B * length / average)
        return {
            index: self.idf(index) * (count * (K1 + 1.0)) / (count + normaliser)
            for index, count in counts.items()
        }

    def query_vector(self, tokens: list[str]) -> dict[int, float]:
        """The query side of the same score."""
        counts: dict[int, int] = {}
        for token in tokens:
            index = self.vocabulary.get(token)
            if index is not None:
                counts[index] = counts.get(index, 0) + 1
        return {
            index: self.idf(index) * (count * (K1 + 1.0)) / (count + K1)
            for index, count in counts.items()
        }


def signal_text(recipe: Recipe) -> str:
    """What the recipe claims to be for."""
    parts = [recipe.summary]
    parts.extend(recipe.when_to_use)
    parts.extend(recipe.not_when_to_use)
    parts.extend(recipe.inputs)
    return chr(10).join(part for part in parts if part)


def detail_text(recipe: Recipe) -> str:
    """The whole recipe: signals plus the procedure."""
    parts = [signal_text(recipe)]
    parts.extend(step.title + " " + step.detail for step in recipe.steps)
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


def _spaces(recipes: list[Recipe]) -> tuple[Bm25Space, Bm25Space]:
    signals = Bm25Space().fit({r.id: tokenize(signal_text(r)) for r in recipes})
    details = Bm25Space().fit({r.id: tokenize(detail_text(r)) for r in recipes})
    return signals, details


def build(recipes: list[Recipe], path: Path | None = None) -> Path:
    """Build the vector index of the library and return its path."""
    if not ZVEC_AVAILABLE:
        raise RuntimeError("zvec is not installed: pip install 'envwiki[vector]'")

    target = path or index_path(recipes)
    target.parent.mkdir(parents=True, exist_ok=True)

    signals, details = _spaces(recipes)
    settings = dense_settings()

    vectors: list[Any] = [
        VectorSchema(
            "signal",
            DataType.SPARSE_VECTOR_FP32,
            dimension=0,
            index_param=FlatIndexParam(),
        ),
        VectorSchema(
            "detail",
            DataType.SPARSE_VECTOR_FP32,
            dimension=0,
            index_param=FlatIndexParam(),
        ),
    ]
    embeddings: list[list[float]] = []
    if settings:
        base, model, api_key = settings
        embeddings = embed([detail_text(recipe) for recipe in recipes], base, model, api_key)
        vectors.append(
            VectorSchema(
                "dense",
                DataType.VECTOR_FP32,
                dimension=len(embeddings[0]),
                index_param=HnswIndexParam(),
            )
        )

    schema = CollectionSchema(
        name="recipes",
        fields=[
            FieldSchema("id", DataType.STRING, nullable=False),
            FieldSchema(
                "body",
                DataType.STRING,
                nullable=False,
                index_param=FtsIndexParam(tokenizer_name="standard", filters=["lowercase"]),
            ),
            FieldSchema("family", DataType.STRING, nullable=True),
            FieldSchema("effort", DataType.STRING, nullable=True),
        ],
        vectors=vectors,
    )

    staging = Path(tempfile.mkdtemp(prefix="envwiki-index-", dir=str(target.parent)))
    collection = zvec.create_and_open(path=str(staging / "recipes"), schema=schema)
    try:
        docs = []
        for position, recipe in enumerate(recipes):
            doc_vectors: dict[str, Any] = {
                "signal": signals.document_vector(tokenize(signal_text(recipe))),
                "detail": details.document_vector(tokenize(detail_text(recipe))),
            }
            if embeddings:
                doc_vectors["dense"] = embeddings[position]
            docs.append(
                zvec.Doc(
                    id=recipe.id,
                    fields={
                        "id": recipe.id,
                        "body": detail_text(recipe),
                        "family": recipe.family,
                        "effort": recipe.effort,
                    },
                    vectors=doc_vectors,
                )
            )
        collection.insert(docs)
        collection.flush()
    finally:
        collection.close()

    if target.exists():
        shutil.rmtree(target)
    os.replace(staging / "recipes", target)
    shutil.rmtree(staging, ignore_errors=True)
    return target


def search(
    recipes: list[Recipe],
    profile: str,
    limit: int = 6,
) -> list[tuple[str, float]] | None:
    """Rank the recipes by vector similarity, or None when there is no index.

    The scores are relative: the best match is 1.0 and the rest are scaled to
    it, so they can be compared with the lexical scores.
    """
    if not ZVEC_AVAILABLE:
        return None

    path = index_path(recipes)
    if not path.exists():
        try:
            build(recipes, path)
        except Exception:
            return None

    signals, details = _spaces(recipes)
    tokens = tokenize(profile)
    queries = [
        Query(field_name="signal", vector=signals.query_vector(tokens)),
        Query(field_name="detail", vector=details.query_vector(tokens)),
    ]
    settings = dense_settings()
    if settings:
        base, model, api_key = settings
        try:
            queries.append(
                Query(
                    field_name="dense",
                    vector=embed([profile], base, model, api_key)[0],
                )
            )
        except Exception:
            pass

    try:
        collection = zvec.open(path=str(path))
    except Exception:
        return None
    try:
        try:
            results = collection.query(
                queries=[
                    *queries,
                    Query(field_name="body", fts=Fts(match_string=profile)),
                ],
                topk=limit,
                reranker=RrfReRanker(rank_constant=60),
            )
        except Exception:
            results = collection.query(
                queries=queries,
                topk=limit,
                reranker=RrfReRanker(rank_constant=60),
            )
    except Exception:
        return None
    finally:
        try:
            collection.close()
        except Exception:
            pass

    hits = [(str(doc.id), float(doc.score)) for doc in results]
    if not hits:
        return []
    best = max(score for _, score in hits) or 1.0
    return [(recipe_id, score / best) for recipe_id, score in hits]


def engine() -> str:
    """Which engine answers a query right now."""
    if not ZVEC_AVAILABLE:
        return "lexical"
    return "zvec-hybrid" if dense_settings() else "zvec-bm25"
