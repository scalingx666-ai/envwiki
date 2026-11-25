"""Tests for the structured shape of the recipe library.

A recipe is read by an agent that has to choose between methods and then
follow one. The library is only useful if the choices can be compared by
fields, and if the steps it lists are steps one task can actually take.
"""

from __future__ import annotations

import json

from envwiki.recipes import load_library

MATERIAL_KINDS = {
    "code", "web", "gui", "api", "data", "simulation", "multi-agent",
    "embodied", "trajectory", "specification", "infrastructure", "paper",
}
TASK_KINDS = {
    "implement", "repair", "reverse", "optimize", "extend", "reproduce", "none",
}
ROLES = {"create", "environment", "verify", "curate"}

SUMMARY_LIMIT = 220


def test_every_recipe_declares_its_material_kind():
    library = load_library()
    for recipe in library.recipes:
        assert recipe.material_kind, recipe.id
        assert set(recipe.material_kind) <= MATERIAL_KINDS, recipe.id


def test_every_recipe_declares_its_task_kind_and_role():
    library = load_library()
    for recipe in library.recipes:
        assert recipe.task_kind in TASK_KINDS, recipe.id
        assert recipe.role in ROLES, recipe.id


def test_every_recipe_declares_what_it_needs_and_produces():
    library = load_library()
    for recipe in library.recipes:
        assert recipe.needs, recipe.id
        assert recipe.produces, recipe.id


def test_the_summary_is_a_summary():
    """A card is compared at a glance, so the summary stays short."""
    library = load_library()
    for recipe in library.recipes:
        assert len(recipe.summary) <= SUMMARY_LIMIT, (
            recipe.id, len(recipe.summary)
        )


def test_the_background_keeps_the_longer_distillation():
    library = load_library()
    for recipe in library.recipes:
        assert recipe.background, recipe.id


def test_the_verification_family_never_claims_to_make_a_task():
    """A method that checks tasks must not look like one that makes them."""
    library = load_library()
    for recipe in library.recipes:
        if recipe.family == "verification":
            assert recipe.role != "create", recipe.id
            assert recipe.task_kind == "none", recipe.id


def test_every_step_says_how_it_is_done():
    library = load_library()
    for recipe in library.recipes:
        for step in recipe.steps:
            assert "accept" in step.model_dump(), (recipe.id, step.title)


def test_the_plan_stays_small():
    """Choosing a method must not cost a wall of prose.

    The plan carries three cards and the procedure of the top one. Before
    the library was restructured the same call returned every candidate
    full prose and cost over ten thousand characters; it now has to stay
    well under half of that.
    """
    library = load_library()
    plan = library.plan("a python repository with a cli, offline checks", limit=3)
    blob = json.dumps(plan, ensure_ascii=False)
    assert len(blob) < 6500, len(blob)


def test_the_candidates_are_cards_and_only_the_top_one_is_expanded():
    library = load_library()
    plan = library.plan("a python repository with a cli, offline checks", limit=3)
    for entry in plan[1:]:
        assert "steps" not in entry
        assert "source_papers" not in entry
        assert "verifier" not in entry
    assert "steps" in plan[0]
    assert plan[0]["source_papers"]


def test_the_plan_gives_the_steps_of_the_best_match_only():
    library = load_library()
    plan = library.plan("a python repository with a cli, offline checks", limit=3)
    assert "steps" in plan[0]
    for entry in plan[1:]:
        assert "steps" not in entry


def test_the_plan_carries_the_facets():
    library = load_library()
    plan = library.plan("a python repository with a cli, offline checks", limit=3)
    for entry in plan:
        assert entry["material_kind"], entry["id"]
        assert entry["task_kind"], entry["id"]
        assert entry["role"], entry["id"]


def test_the_card_does_not_carry_the_procedure():
    library = load_library()
    card = library.card(library.recipes[0])
    assert "steps" not in card
    assert "background" not in card


def test_a_material_kind_in_the_profile_ranks_its_recipes_first():
    """The fields are what the agent compares, so they have to count."""
    library = load_library()
    hits = library.search("a code repository, repair a defect", limit=5)
    assert hits, "nothing matched"
    top = hits[0][0]
    assert "code" in top.material_kind or top.task_kind == "repair", top.id


def test_the_material_decides_the_order_before_the_prose():
    """A profile that names a material gets that material back.

    The tier the structured fields put a recipe in decides the order, so
    the recipes that work on the material the profile names come first.
    """
    library = load_library()
    hits = library.search("a python repository with a cli", limit=5)
    assert hits
    for recipe, _ in hits:
        assert "code" in recipe.material_kind, recipe.id


def test_the_same_question_gets_the_same_answer():
    """A recommendation must not depend on which process answered it.

    The index used to rank with an approximate vector top-k, so two
    processes asking the same question got different recipes back.
    """
    library = load_library()
    query = "a python repository with a cli, offline checks"
    first = [recipe.id for recipe, _ in library.search(query, limit=6)]
    second = [recipe.id for recipe, _ in library.search(query, limit=6)]
    assert first == second