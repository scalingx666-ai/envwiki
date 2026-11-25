"""Tests for the vector index over the recipe library."""

from __future__ import annotations

import pytest

from envwiki.recipes import vector_index
from envwiki.recipes.library import load_library


@pytest.fixture(autouse=True)
def _index_dir(tmp_path, monkeypatch):
    """Keep the index out of the user cache directory."""
    monkeypatch.setenv("ENVWIKI_INDEX_DIR", str(tmp_path))


def test_library_reports_the_engine_it_uses():
    assert load_library().engine() in {"lexical", "zvec-fts", "zvec-fts+dense"}


def test_library_falls_back_to_the_lexical_matcher(monkeypatch):
    monkeypatch.setattr(vector_index, "ZVEC_AVAILABLE", False)
    library = load_library()
    assert library.engine() == "lexical"
    hits = library.search("a python cli that converts csv to json", limit=3)
    assert hits
    assert hits[0][1] > 0


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


@pytest.mark.skipif(not vector_index.ZVEC_AVAILABLE, reason="zvec is not installed")
def test_the_index_version_is_part_of_the_fingerprint():
    """An index built by an older layout must never be reused."""
    recipes = load_library().recipes
    before = vector_index.fingerprint(recipes)
    version = vector_index.INDEX_VERSION
    try:
        vector_index.INDEX_VERSION = version + "-other"
        assert vector_index.fingerprint(recipes) != before
    finally:
        vector_index.INDEX_VERSION = version