"""envwiki as an MCP server: the toolbox an agent uses to build a task.

The server holds no synthesis logic of its own. It offers three kinds of
thing, and the agent decides how to use them:

- recipes: environment and task synthesis methods, distilled from the
  papers that describe them;
- material: a staging area where links and uploads are resolved into
  something an agent can explore;
- scaffolding: writing and checking a Harbor task directory.

The agent picks a method, follows it, and calls the scaffolding tools. The
server only executes what it is asked to execute, and validates the result.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from envwiki import __version__
from envwiki.convert.builder import (
    detect_recipes,
    missing_staged_assets,
    write_task,
)
from envwiki.convert.gate import gate_task as run_gate
from envwiki.convert.validate import validate_task
from envwiki.ingest.bundle import build_bundle, build_tree
from envwiki.recipes import load_library
from envwiki.schemas import (
    EnvironmentSpec,
    Provenance,
    SolutionSpec,
    TaskDraft,
    TaskMetadata,
    VerifierSpec,
)

INSTRUCTIONS = """\
envwiki gives you the material, the methods and the scaffolding to build a
Harbor benchmark task.

It does not decide what the task should be. You do. Nothing is
staged for you either: start with stage_source.

- stage_source brings a link or an upload into a workspace you can explore;
- plan_task and get_recipe give you synthesis methods distilled from the
  literature: read one, then follow its steps;
- scaffold_task writes the task directory from the spec you produce;
- validate_task checks that directory against Harbor's own schema;
- gate_task runs the task and checks that it really works.

Workflow: stage the material, describe it, ask for a method, follow the
method, scaffold the task, validate it, gate it, and fix whatever the
validator or the gate reports.

The gate is the part that matters. A task that parses can still be
broken: the reference solution has to earn the full reward when the task
is really run, and an agent that does nothing must earn less.
"""

server = MCPServer(
    name="envwiki",
    version=__version__,
    instructions=INSTRUCTIONS,
)


def _summary(recipe, score: float | None = None) -> dict[str, Any]:
    """The card a ranking tool returns: fields to compare, not prose.

    The fields say what kind of material the method works on, what kind of
    task it poses and what it needs, so an agent can choose without
    reading the long method first. get_recipe has the rest.
    """
    data: dict[str, Any] = {
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
    if score is not None:
        data["match_score"] = round(score, 4)
    return data


# ---------------------------------------------------------------- recipes


@server.tool(
    name="list_recipes",
    description=(
        "List every synthesis recipe, optionally filtered by family "
        "(environment-synthesis, web-gui, terminal-coding, verification, ...) "
        "or by effort (low, medium, high)."
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
            "known_ids": [r.id for r in library.recipes],
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
    return {"count": len(recipes), "engine": library.engine(), "recipes": recipes}


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
    return {"count": len(recipes), "engine": library.engine(), "recipes": recipes}


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
    return {"count": len(plan), "engine": library.engine(), "plan": plan}


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


# ---------------------------------------------------------------- material


@server.tool(
    name="stage_source",
    description=(
        "Resolve source material into a workspace you can explore: a GitHub "
        "link is cloned, any other URL is read through the reader, uploads are "
        "extracted. Returns the staging directory, the file tree and a digest "
        "with a line-number index so you can jump straight to what you need."
    ),
)
def stage_source(
    urls: list[str] | None = None,
    uploads: list[str] | None = None,
    workspace: str = "",
) -> dict[str, Any]:
    """Stage links and uploads into an explorable workspace."""
    target = Path(workspace).expanduser() if workspace else Path(
        tempfile.mkdtemp(prefix="envwiki-stage-")
    )
    try:
        bundle = build_bundle(
            list(urls or []),
            [Path(u) for u in (uploads or [])],
            target,
        )
    except Exception as exc:
        return {
            "error": "could not stage the material: "
            + type(exc).__name__ + ": " + str(exc)[:400],
            "hint": "check the url and that the workspace is writable",
        }
    return {
        "staging_dir": str(bundle.staging_dir),
        "tree": bundle.tree,
        "digest": bundle.digest,
        "sources": [source.model_dump() for source in bundle.sources],
        "images": [str(p) for p in bundle.images],
        "warnings": bundle.warnings,
    }


@server.tool(
    name="list_staged",
    description="List what is currently staged under a workspace directory.",
)
def list_staged(staging_dir: str) -> dict[str, Any]:
    """Return the file tree of a staging directory."""
    root = Path(staging_dir).expanduser()
    if not root.is_dir():
        return {"error": "not a directory: " + str(root)}
    return {"staging_dir": str(root), "tree": build_tree(root)}


# ---------------------------------------------------------------- scaffolding


def _target_dir(task_dir: str, staging: Path | None, name: str) -> tuple[Path, str]:
    """Where the task should be written, and a note when it could not go there.

    An agent that asks for a path it cannot write to still gets its task: it
    lands in the workspace instead, and the note says so.
    """
    if task_dir:
        out = Path(task_dir).expanduser()
        try:
            out.mkdir(parents=True, exist_ok=True)
            probe = out / ".envwiki-write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return out, ""
        except OSError as exc:
            if staging is not None:
                return (
                    staging / "tasks" / name,
                    "task_dir '"
                    + str(out)
                    + "' is not writable ("
                    + type(exc).__name__
                    + ": "
                    + str(exc)
                    + "); the task was written into the workspace instead",
                )
            return out, ""
    if staging is not None:
        return staging / "tasks" / name, ""
    return Path(tempfile.mkdtemp(prefix="envwiki-task-")) / name, ""


@server.tool(
    name="scaffold_task",
    description=(
        "Write a Harbor task directory from the spec you produced. This is "
        "the only way to materialise a task, so the spec shape is enforced "
        "here rather than in prose: instruction_md is the task text the "
        "solving agent sees, verifier_code is the test that writes "
        "/logs/verifier/reward.txt, solution_code is the reference solution. "
        "Files listed in copy_from_staging are copied into the image and "
        "land at the root of the working directory under their own file name. "
        "Pass staging_dir to write into that workspace (the task lands in "
        "<staging>/tasks/<name>); task_dir overrides the location and must be "
        "writable, and if it is not the task goes into the workspace instead "
        "and the answer says so. Call validate_task on the result, then "
        "gate_task to find out whether it really runs. The task name is "
        "prefixed with the org you pass. Pin the material with "
        "upstream_repo and upstream_commit so the task can be rebuilt, and "
        "set reward_floor when the task starts from a partly working state."
    ),
)
def scaffold_task(
    name: str,
    instruction_md: str,
    verifier_code: str,
    description: str = "",
    verifier_language: str = "bash",
    solution_code: str = "",
    solution_language: str = "bash",
    base_image: str = "ubuntu:24.04",
    workdir: str = "/app",
    target_os: str = "linux",
    setup_commands: list[str] | None = None,
    copy_from_staging: list[str] | None = None,
    difficulty: str = "unrated",
    category: str = "general",
    tags: list[str] | None = None,
    source_notes: str = "",
    upstream_repo: str = "",
    upstream_commit: str = "",
    upstream_license: str = "",
    derived_from: str = "",
    reward_floor: float | None = None,
    staging_dir: str = "",
    task_dir: str = "",
    org: str = "envwiki",
) -> dict[str, Any]:
    """Materialise a Harbor task directory from a spec."""
    try:
        draft = TaskDraft(
            name=name,
            description=description,
            metadata=TaskMetadata(
                difficulty=difficulty,
                category=category,
                tags=list(tags or []),
                provenance=Provenance(
                    upstream_repo=upstream_repo,
                    upstream_commit=upstream_commit,
                    upstream_license=upstream_license,
                    derived_from=derived_from,
                ),
            ),
            instruction_md=instruction_md,
            environment=EnvironmentSpec(
                base_image=base_image,
                workdir=workdir,
                os=target_os,
                setup_commands=list(setup_commands or []),
                copy_from_staging=list(copy_from_staging or []),
            ),
            verifier=VerifierSpec(language=verifier_language, code=verifier_code),
            solution=(
                SolutionSpec(language=solution_language, code=solution_code)
                if solution_code.strip()
                else None
            ),
            source_notes=source_notes,
            reward_floor=reward_floor,
        )
    except Exception as exc:
        return {
            "error": "the task spec was not usable: "
            + type(exc).__name__ + ": " + str(exc)[:400],
            "hint": "instruction_md and verifier_code are required",
        }

    staging_value = staging_dir or os.environ.get("ENVWIKI_STAGING_DIR", "")
    staging = Path(staging_value).expanduser() if staging_value else None
    out, note = _target_dir(task_dir, staging, draft.name)
    try:
        written = write_task(draft, out, staging_dir=staging, org=org)
    except Exception as exc:
        return {
            "error": "could not write the task to '"
            + str(out) + "': " + type(exc).__name__ + ": " + str(exc)[:400],
            "staging_dir": str(staging) if staging else "",
            "hint": "pass staging_dir so the task lands in the workspace",
        }

    answer = {
        "task_dir": str(written),
        "name": draft.name,
        "org": org,
        "recipes": detect_recipes(draft.source_notes + chr(10) + draft.instruction_md),
        "files": sorted(
            str(p.relative_to(written)) for p in written.rglob("*") if p.is_file()
        ),
        "missing_assets": missing_staged_assets(
            list(copy_from_staging or []), staging
        ),
    }
    if note:
        answer["note"] = note
    return answer


@server.tool(
    name="gate_task",
    description=(
        "Run the task and check it really works. This is the execution "
        "gate: the reference solution has to earn the full reward when the "
        "task is actually run, and an agent that does nothing must earn "
        "less, so the task leaves reward space to compete for. It also "
        "checks that the instruction does not hand out the answer. Needs "
        "Harbor and a running Docker daemon; when either is missing it "
        "says so instead of pretending the task passed. Call it after "
        "validate_task, and fix whatever it reports."
    ),
)
def gate_task(
    task_dir: str,
    run_oracle: bool = True,
    run_baseline: bool = True,
    timeout_sec: float = 1800.0,
) -> dict[str, Any]:
    """Run the execution-level gate over a task directory."""
    try:
        report = run_gate(
            Path(task_dir).expanduser(),
            timeout_sec=timeout_sec,
            run_oracle=run_oracle,
            run_baseline=run_baseline,
        )
    except Exception as exc:
        return {
            "ok": False,
            "verified": False,
            "task_dir": task_dir,
            "errors": [type(exc).__name__ + ": " + str(exc)[:400]],
            "warnings": [],
            "checks": [],
        }
    return {
        "ok": report.ok,
        "verified": report.verified,
        "task_dir": report.task_dir,
        "reward": report.reward,
        "floor": report.floor,
        "reward_repair": report.reward_repair,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
                "measured": check.measured,
            }
            for check in report.checks
        ],
        "errors": report.errors,
        "warnings": report.warnings,
        "notes": report.notes,
    }


@server.tool(
    name="validate_task",
    description=(
        "Check a task directory: the local structure plus Harbor's own "
        "TaskConfig when Harbor is importable. Returns the errors and the "
        "warnings you have to fix."
    ),
)
def validate_task_tool(task_dir: str) -> dict[str, Any]:
    """Validate a task directory against Harbor's schema."""
    try:
        report = validate_task(Path(task_dir).expanduser())
    except Exception as exc:
        return {
            "ok": False,
            "task_dir": task_dir,
            "errors": [type(exc).__name__ + ": " + str(exc)[:400]],
            "warnings": [],
        }
    return {
        "ok": report.ok,
        "task_dir": report.task_dir,
        "schema_source": report.schema_source,
        "errors": [i.message for i in report.errors],
        "warnings": [i.message for i in report.warnings],
    }


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
