"""envwiki as an MCP server.

The recipe library (environment/task synthesis methods distilled from the
literature) is served here, so any agent harness that speaks MCP can look up
the method that fits the source material and follow it.

Run it directly:

    envwiki-mcp                  # stdio, the usual way for a local harness
    envwiki-mcp --transport streamable-http --port 8765

Or let a harness spawn it: see envwiki.harness.pi_harness.build_mcp_config.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from envwiki import __version__
from envwiki.recipes import load_library

INSTRUCTIONS = """envwiki serves a library of environment and task synthesis recipes.

Each recipe is one abstract method, distilled from the papers that describe it:
when it applies, what it needs, the procedure to follow, and how to make the
result deterministically verifiable.

Typical use: describe the source material you are working from, call
recommend_recipes to get candidate methods, call get_recipe for the full
procedure of the one that fits, then build the task that the recipe describes.
"""

server = MCPServer(
    name="envwiki",
    version=__version__,
    instructions=INSTRUCTIONS,
)


def _summary(recipe, score: float | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": recipe.id,
        "name": recipe.name,
        "family": recipe.family,
        "effort": recipe.effort,
        "summary": recipe.summary,
        "when_to_use": recipe.when_to_use,
        "not_when_to_use": recipe.not_when_to_use,
        "source_papers": [
            {"arxiv_id": paper.arxiv_id, "title": paper.title, "note": paper.note}
            for paper in recipe.source_papers
        ],
    }
    if score is not None:
        data["match_score"] = round(score, 4)
    return data


@server.tool(
    name="list_recipes",
    description=(
        "List every synthesis recipe, optionally filtered by family "
        "(web-gui, terminal, simulation, ...) or by effort (low, medium, high)."
    ),
)
def list_recipes(family: str = "", effort: str = "") -> dict[str, Any]:
    """Return the recipe index."""
    library = load_library()
    recipes = library.summaries(family=family.strip(), effort=effort.strip())
    return {"count": len(recipes), "recipes": recipes}


@server.tool(
    name="get_recipe",
    description=(
        "Get one recipe in full: the procedure steps, the required inputs, "
        "how to verify the outcome, the pitfalls, and the papers it came from."
    ),
)
def get_recipe(recipe_id: str) -> dict[str, Any]:
    """Return one recipe by id."""
    library = load_library()
    recipe = library.get(recipe_id)
    if recipe is None:
        return {
            "error": "unknown recipe: " + recipe_id,
            "known_ids": [r.id for r in library.recipes][:40],
        }
    return recipe.model_dump()


@server.tool(
    name="search_recipes",
    description="Search recipes by keyword and return the best matches.",
)
def search_recipes(query: str, limit: int = 6) -> dict[str, Any]:
    """Rank recipes by keyword overlap."""
    library = load_library()
    recipes = [_summary(recipe, score) for recipe, score in library.search(query, limit=limit)]
    return {"count": len(recipes), "recipes": recipes}


@server.tool(
    name="recommend_recipes",
    description=(
        "Describe the source material you have (a repository, a document, a "
        "dataset, a web app, a terminal tool) and get the recipes that fit it, "
        "ranked. Use this first, then fetch the chosen recipe with get_recipe."
    ),
)
def recommend_recipes(source_profile: str, limit: int = 5) -> dict[str, Any]:
    """Rank recipes by fit to a description of the source material."""
    library = load_library()
    recipes = [
        _summary(recipe, score)
        for recipe, score in library.recommend(source_profile, limit=limit)
    ]
    return {"count": len(recipes), "recipes": recipes}


@server.tool(
    name="plan_task",
    description=(
        "One round trip: describe the source material and get the ranked "
        "methods, with the full procedure of the best match. Use this instead "
        "of recommend_recipes when you intend to follow the top result."
    ),
)
def plan_task(source_profile: str, limit: int = 3) -> dict[str, Any]:
    """Rank recipes by fit and expand the best one into a procedure."""
    library = load_library()
    plan = library.plan(source_profile, limit=limit)
    return {"count": len(plan), "plan": plan}


@server.tool(
    name="list_recipe_families",
    description="List the recipe families with the number of recipes in each.",
)
def list_recipe_families() -> dict[str, Any]:
    """Return the family histogram."""
    library = load_library()
    return {
        "families": library.families(),
        "total_recipes": len(library.recipes),
    }


@server.resource(
    "envwiki://recipes/index",
    name="Recipe index",
    description="Every recipe as one JSON document.",
)
def recipe_index() -> str:
    """Return the whole library as JSON."""
    library = load_library()
    return json.dumps(
        {"recipes": [r.model_dump() for r in library.recipes]}, indent=2, ensure_ascii=False
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the envwiki MCP server.")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="Transport to serve on (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.transport == "stdio":
        server.run(transport="stdio")
        return
    server.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
