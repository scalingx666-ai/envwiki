"""Tests for the synthesis recipe library."""

from __future__ import annotations

import re
from pathlib import Path

from envwiki.recipes import corpus_size, is_grounded, load_library
from envwiki.recipes.schema import Recipe

ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}$")

EXPECTED_FAMILIES = {
    "computer-use",
    "data-synthesis",
    "embodied",
    "enterprise-professional",
    "environment-synthesis",
    "experience-synthesis",
    "mcp-tools",
    "multi-agent",
    "platform-infra",
    "sandbox",
    "simulation",
    "task-scenario",
    "terminal-coding",
    "verification",
    "web-gui",
}


def test_library_loads_with_recipes():
    library = load_library()
    assert len(library.recipes) >= 25
    assert library.families()


def test_every_recipe_is_well_formed():
    library = load_library()
    seen: set[str] = set()
    for recipe in library.recipes:
        assert recipe.id not in seen, "duplicate id " + recipe.id
        seen.add(recipe.id)
        assert len(recipe.steps) >= 5, recipe.id
        assert recipe.summary.strip(), recipe.id
        assert recipe.when_to_use, recipe.id
        assert recipe.inputs, recipe.id
        assert recipe.verifier, recipe.id
        assert recipe.pitfalls, recipe.id
        assert recipe.effort in {"low", "medium", "high"}
        assert len(recipe.source_papers) >= 2, recipe.id
        for paper in recipe.source_papers:
            assert ARXIV_ID_RE.match(paper.arxiv_id), paper.arxiv_id
            assert paper.title.strip(), recipe.id


def test_every_citation_is_grounded_in_the_corpus():
    library = load_library()
    for recipe in library.recipes:
        for paper in recipe.source_papers:
            assert is_grounded(paper.arxiv_id), (
                recipe.id + " cites " + paper.arxiv_id + ", which is not in the corpus"
            )


def test_cited_titles_match_the_corpus():
    from envwiki.recipes import load_corpus

    def norm(text):
        return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())

    corpus = load_corpus()
    library = load_library()
    for recipe in library.recipes:
        for paper in recipe.source_papers:
            entry = corpus.get(paper.arxiv_id)
            assert entry is not None, paper.arxiv_id
            assert entry["title"], paper.arxiv_id
            assert norm(entry["title"]) == norm(paper.title), (
                recipe.id + " titles " + paper.arxiv_id + " as " + paper.title
            )


def test_corpus_is_the_reading_list():
    assert corpus_size() > 500


def test_expected_families_are_covered():
    library = load_library()
    families = set(library.families())
    missing = EXPECTED_FAMILIES - families
    assert not missing, "families missing: " + ", ".join(sorted(missing))


def test_search_finds_the_right_recipe():
    library = load_library()
    hits = library.search("docker container fail-to-pass verifier", limit=3)
    assert hits
    assert any("terminal" in recipe.family for recipe, _ in hits)


def test_recommend_ranks_a_gui_source_into_the_gui_family():
    library = load_library()
    hits = library.recommend(
        "a web application to reconstruct as a lightweight gui environment "
        "with assertions over the dom",
        limit=3,
    )
    assert hits
    assert hits[0][0].family == "web-gui"


def test_plan_expands_the_best_match():
    library = load_library()
    plan = library.plan(
        "a python CLI that converts CSV to JSON in a terminal sandbox",
        limit=2,
    )
    assert plan
    assert plan[0]["rank"] == 1
    assert "steps" in plan[0]
    assert len(plan[0]["steps"]) >= 5
    assert "steps" not in plan[1]


def test_recipe_files_are_one_per_family():
    data_dir = Path(__file__).parents[1] / "src" / "envwiki" / "recipes" / "data" / "families"
    files = sorted(p.stem for p in data_dir.glob("*.json"))
    assert files
    assert len(files) == len(set(files))
    library = load_library()
    for family in library.families():
        assert family in files, family


def test_detect_recipes_records_the_method_used():
    from envwiki.convert.builder import detect_recipes

    library = load_library()
    recipe = library.recipes[0]
    assert detect_recipes("I followed " + recipe.id + " for this task") == [recipe.id]
    assert detect_recipes("no recipe mentioned here") == []
    assert detect_recipes("") == []


def test_model_round_trip():
    library = load_library()
    for recipe in library.recipes:
        assert Recipe.model_validate(recipe.model_dump()).id == recipe.id


def test_library_can_be_loaded_from_an_explicit_path(tmp_path: Path):
    path = tmp_path / "recipes.json"
    path.write_text(
        '{"recipes": [{"id": "x", "name": "X", "family": "f", "summary": "s", '
        '"when_to_use": ["a"], "inputs": ["b"], "steps": [{"title": "t", "detail": "d"}], '
        '"verifier": ["v"], "pitfalls": ["p"], "effort": "low", '
        '"source_papers": [{"arxiv_id": "2401.00001", "title": "T"}]}]}',
        encoding="utf-8",
    )
    library = load_library(str(path))
    assert len(library.recipes) == 1
    assert library.get("x") is not None
