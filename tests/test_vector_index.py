"""Tests for the vector index over the recipe library."""

from __future__ import annotations

import pytest

from envwiki.recipes import vector_index
from envwiki.recipes.library import load_library


@pytest.fixture(autouse=True)
def _index_dir(tmp_path, monkeypatch):
    """Keep the index out of the user's cache directory."""
    monkeypatch.setenv("ENVWIKI_INDEX_DIR", str(tmp_path))


def test_bm25_space_ranks_the_document_that_mentions_the_term():
    documents = {
        "a": vector_index.tokenize("dockerise a terminal coding task"),
        "b": vector_index.tokenize("synthesise a web gui environment"),
        "c": vector_index.tokenize("verify a task with state diffs"),
    }
    space = vector_index.Bm25Space().fit(documents)
    query = space.query_vector(vector_index.tokenize("terminal coding"))
    scores = {
        key: sum(
            query[index] * space.document_vector(tokens).get(index, 0.0)
            for index in query
        )
        for key, tokens in documents.items()
    }
    assert scores["a"] > scores["b"]
    assert scores["b"] >= scores["c"]


def test_bm25_idf_favours_the_rare_term():
    space = vector_index.Bm25Space().fit(
        {"a": ["docker", "cli"], "b": ["docker", "gui"], "c": ["docker", "web"]}
    )
    assert space.idf(space.vocabulary["cli"]) > space.idf(space.vocabulary["docker"])


def test_library_reports_the_engine_it_uses():
    assert load_library().engine() in {"lexical", "zvec-bm25", "zvec-hybrid"}


def test_library_still_ranks_recipes():
    hits = load_library().search("a python cli that converts csv to json", limit=3)
    assert hits
    assert hits[0][1] > 0
    assert hits[0][0].id


@pytest.mark.skipif(not vector_index.ZVEC_AVAILABLE, reason="zvec is not installed")
def test_vector_index_finds_the_recipe_that_fits():
    recipes = load_library().recipes
    hits = vector_index.search(recipes, "a web application with a login form", limit=3)
    assert hits
    assert hits[0][1] == 1.0
    by_id = {recipe.id: recipe for recipe in recipes}
    assert by_id[hits[0][0]].family == "web-gui"


@pytest.mark.skipif(not vector_index.ZVEC_AVAILABLE, reason="zvec is not installed")
def test_vector_index_is_cached_on_disk():
    recipes = load_library().recipes
    path = vector_index.index_path(recipes)
    assert not path.exists()
    vector_index.search(recipes, "a python cli", limit=2)
    assert path.exists()


@pytest.mark.skipif(not vector_index.ZVEC_AVAILABLE, reason="zvec is not installed")
def test_a_changed_library_gets_its_own_index():
    recipes = load_library().recipes
    first = vector_index.index_path(recipes)
    second = vector_index.index_path(recipes + [recipes[0]])
    assert first != second
