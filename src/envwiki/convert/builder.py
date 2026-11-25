"""Turn a TaskDraft into a Harbor task directory.

Harbor's execution contract drives the shape of what is written here:

- the verifier is discovered as tests/test.sh and the reference solution
  as solution/solve.sh, and only that one file per directory is uploaded
  into the container;
- a verifier that wants to score several checks writes them to
  /logs/verifier/reward.json, and the reward is the mean of the checks;
- a floor is the reward an unfixed build still earns, and it makes the
  remaining reward space explicit.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from envwiki.recipes import load_library
from envwiki.schemas import TaskDraft

#: Harbor discovers one script per directory and uploads only that file.
SOLUTION_NAME = "solve.sh"
VERIFIER_NAME = "test.sh"
DEFAULT_ORG = "envwiki"

NL = chr(10)


def _toml_str(value: str) -> str:
    """Quote a value as a TOML basic string (JSON escaping is TOML-compatible)."""
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: list[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _toml_table(name: str, values: dict[str, object]) -> list[str]:
    """Render a nested table such as [metadata.provenance]."""
    lines = ["[" + name + "]"]
    for key, value in values.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key} = {value}")
        elif isinstance(value, (list, tuple)):
            lines.append(f"{key} = {_toml_array([str(v) for v in value])}")
        elif isinstance(value, dict):
            lines.append(f"{key} = {_toml_str(json.dumps(value, ensure_ascii=False))}")
        else:
            lines.append(f"{key} = {_toml_str(str(value))}")
    lines.append("")
    return lines


def render_task_toml(draft: TaskDraft, *, org: str = DEFAULT_ORG, author: str | None = None) -> str:
    """Render the task.toml for a draft."""
    meta = draft.metadata
    lines: list[str] = ['schema_version = "1.4"', ""]

    lines.append("[task]")
    lines.append(f"name = {_toml_str(org + '/' + draft.name)}")
    if draft.description:
        lines.append(f"description = {_toml_str(draft.description)}")
    if author:
        lines.append(f"authors = {_toml_array([author])}")
    lines.append("")

    lines.append("[metadata]")
    lines.append(f"difficulty = {_toml_str(meta.difficulty)}")
    lines.append(f"category = {_toml_str(meta.category)}")
    if meta.tags:
        lines.append(f"tags = {_toml_array(meta.tags)}")
    lines.append("")

    provenance = meta.provenance
    if provenance.upstream_repo or provenance.derived_from:
        lines.extend(
            _toml_table(
                "metadata.provenance",
                {
                    "upstream_repo": provenance.upstream_repo,
                    "upstream_commit": provenance.upstream_commit,
                    "upstream_license": provenance.upstream_license,
                    "source_archive_sha256": provenance.source_archive_sha256,
                    "derived_from": provenance.derived_from,
                },
            )
        )

    if meta.difficulty_facts:
        # Measured facts, not a hand-written tier: they say how the task
        # was measured, and by what.
        lines.extend(_toml_table("metadata.difficulty_facts", dict(meta.difficulty_facts)))

    lines.append("[verifier]")
    lines.append(f"timeout_sec = {float(draft.verifier.timeout_sec)}")
    if draft.reward_floor is not None:
        lines.append(f"reward_floor = {float(draft.reward_floor)}")
    lines.append("")

    lines.append("[agent]")
    lines.append("timeout_sec = 1800.0")
    lines.append("")

    lines.append("[environment]")
    lines.append(f"os = {_toml_str(draft.environment.os)}")
    if draft.environment.workdir:
        lines.append(f"workdir = {_toml_str(draft.environment.workdir)}")
    lines.append("build_timeout_sec = 900.0")
    lines.append("")

    return NL.join(lines)


def _normalise_rel(rel: str) -> str:
    return Path(str(rel).strip().lstrip("./")).as_posix()


def asset_destinations(draft: TaskDraft) -> dict[str, str]:
    """Map every staged relative path to its path inside the image.

    A staged file lands at the root of the working directory under its own
    file name, so "repos/x/readme.md" becomes "/app/readme.md". The
    instruction, the verifier and the solution can then all name the same
    simple path. When two staged files share a file name the second one keeps
    its directory structure to avoid a collision.
    """
    destinations: dict[str, str] = {}
    used: set[str] = set()
    for raw in draft.environment.copy_from_staging:
        rel = _normalise_rel(raw)
        if not rel:
            continue
        name = Path(rel).name
        target = rel if name in used else name
        used.add(name)
        destinations[rel] = target
    return destinations


def _needs_python(draft: TaskDraft) -> bool:
    """Whether any entry point shell calls python3."""
    return draft.verifier.language == "python" or bool(
        draft.solution and draft.solution.language == "python"
    )


def _python_setup(base_image: str) -> str:
    """Install python3 on a non-Python base image, or nothing if present."""
    if "python" in base_image.lower():
        return ""
    return (
        "apt-get update && apt-get install -y --no-install-recommends python3 "
        "&& rm -rf /var/lib/apt/lists/*"
    )


def render_dockerfile(draft: TaskDraft, destinations: dict[str, str] | None = None) -> str:
    """Render environment/Dockerfile (the Docker build context is environment/)."""
    env = draft.environment
    workdir = env.workdir or "/app"
    if destinations is None:
        destinations = asset_destinations(draft)
    parts: list[str] = [f"FROM {env.base_image}", ""]

    # A Python verifier or solution becomes a shell script that calls
    # python3. On a bare image that command does not exist, so the task
    # would fail with RewardFileNotFoundError and the gate would catch it
    # only after a full container run. Install python3 at build time.
    setup = _python_setup(env.base_image) if _needs_python(draft) else ""
    if setup and not any("python3" in cmd for cmd in env.setup_commands):
        parts.append("# The entry points are Python; the image must have an interpreter.")
        parts.append("RUN " + setup)
        parts.append("")

    if destinations:
        parts.append("# Material the task depends on, copied from the source material.")
        for target in destinations.values():
            parts.append(f"COPY {target} {workdir}/{target}")
        parts.append("")

    for cmd in env.setup_commands:
        parts.append(f"RUN {cmd}")

    parts.append("")
    parts.append(f"WORKDIR {workdir}")
    parts.append("")
    parts.append('CMD ["sleep", "infinity"]')
    parts.append("")
    return NL.join(parts)


def _ensure_reward_write(code: str, language: str) -> str:
    """Best-effort guarantee that the verifier emits a reward file."""
    if "/logs/verifier/reward" in code:
        return code
    if language == "python":
        return (
            "import pathlib" + NL
            + "pathlib.Path('/logs/verifier').mkdir(parents=True, exist_ok=True)" + NL
            + "pathlib.Path('/logs/verifier/reward.txt').write_text('0')" + NL
            + code
        )
    return (
        "#!/bin/bash" + NL
        + "mkdir -p /logs/verifier" + NL
        + "echo 0 > /logs/verifier/reward.txt" + NL
        + code
    )


def render_verifier_entry(code: str, language: str) -> str:
    """Write tests/test.sh, the only verifier file Harbor discovers.

    Harbor uploads exactly one script per directory into the container, so
    a Python verifier cannot live next to it as a second file: it has to be
    embedded in the entry point that runs it.
    """
    body = _ensure_reward_write(code, language)
    if language == "python":
        return (
            "#!/bin/bash" + NL
            + "# Generated by envwiki: Harbor runs tests/test.sh, and uploads only" + NL
            + "# this file into the container, so the Python verifier travels with it." + NL
            + "set -uo pipefail" + NL
            + "python3 - <<'ENVWIKI_PYTHON_VERIFIER'" + NL
            + body.rstrip() + NL
            + "ENVWIKI_PYTHON_VERIFIER" + NL
        )
    if not body.lstrip().startswith("#!"):
        body = "#!/bin/bash" + NL + "set -uo pipefail" + NL + body
    return body


def render_solution_entry(code: str, language: str, workdir: str = "/app") -> str:
    """Write solution/solve.sh, the only solution file Harbor discovers.

    A Python solution is written into the working directory and then run,
    because a reference solution has to leave the artefact the verifier
    looks at behind. A solution that only defines something and exits
    produces nothing, and the verifier then finds no file.
    """
    if language == "python":
        return (
            "#!/bin/bash" + NL
            + "# Generated by envwiki: Harbor runs solution/solve.sh, and uploads" + NL
            + "# only this file into the container, so the Python solution travels" + NL
            + "# with it." + NL
            + "set -uo pipefail" + NL
            + "mkdir -p " + workdir + NL
            + "cat > " + workdir + "/solution.py <<'ENVWIKI_PYTHON_SOLUTION'" + NL
            + code.rstrip() + NL
            + "ENVWIKI_PYTHON_SOLUTION" + NL
            + "cd " + workdir + NL
            + "python3 " + workdir + "/solution.py" + NL
        )
    if not code.lstrip().startswith("#!"):
        code = "#!/bin/bash" + NL + "set -uo pipefail" + NL + code
    return code


def _copy_staged_assets(
    draft: TaskDraft, out_dir: Path, staging_dir: Path | None, destinations: dict[str, str]
) -> list[str]:
    """Copy referenced source files into the Docker build context."""
    copied: list[str] = []
    if not staging_dir:
        return copied
    staging_root = staging_dir.resolve()
    for rel, target in destinations.items():
        src = (staging_root / rel).resolve()
        if not str(src).startswith(str(staging_root)):
            continue
        if not src.is_file():
            continue
        dest = out_dir / "environment" / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(rel)
    return copied


def missing_staged_assets(paths: list[str], staging_dir: Path | None) -> list[str]:
    """Which of the requested staged files are not there.

    The agent asks for files by their path in the workspace. One that is
    missing cannot be copied into the image, so it is reported instead of
    quietly breaking the build.
    """
    if staging_dir is None:
        return [_normalise_rel(path) for path in paths if _normalise_rel(path)]
    root = Path(staging_dir).expanduser().resolve()
    missing: list[str] = []
    for raw in paths:
        rel = _normalise_rel(raw)
        if not rel:
            continue
        source = (root / rel).resolve()
        if not str(source).startswith(str(root)) or not source.is_file():
            missing.append(rel)
    return missing


def detect_recipes(text: str) -> list[str]:
    """Which synthesis recipes the model says it followed.

    The recipe ids are matched against the library, so the provenance file
    records the method that produced the task.
    """
    if not text:
        return []
    body = text.lower()
    library = load_library()
    return [recipe.id for recipe in library.recipes if recipe.id.lower() in body]


def write_task(
    draft: TaskDraft,
    out_dir: Path,
    *,
    staging_dir: Path | None = None,
    org: str = DEFAULT_ORG,
    author: str | None = None,
) -> Path:
    """Materialise a Harbor task directory and return its path.

    The three managed directories are rebuilt from scratch, so a task that is
    written twice never keeps a stale file. Anything else in the directory is
    left alone: the caller may have pointed at a directory that holds more
    than the task.
    """
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("environment", "solution", "tests"):
        target = out_dir / sub
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

    destinations = asset_destinations(draft)
    copied = _copy_staged_assets(draft, out_dir, staging_dir, destinations)
    if copied:
        draft.environment.copy_from_staging = copied
    # Only the assets that are really there may be copied into the image:
    # a COPY line for a file that was never staged breaks the build.
    present = {rel: target for rel, target in destinations.items() if rel in copied}
    missing = [rel for rel in destinations if rel not in present]

    (out_dir / "task.toml").write_text(
        render_task_toml(draft, org=org, author=author), encoding="utf-8"
    )
    (out_dir / "instruction.md").write_text(
        draft.instruction_md.strip() + NL, encoding="utf-8"
    )
    (out_dir / "environment" / "Dockerfile").write_text(
        render_dockerfile(draft, present), encoding="utf-8"
    )

    verifier_path = out_dir / "tests" / VERIFIER_NAME
    verifier_path.write_text(
        render_verifier_entry(draft.verifier.code, draft.verifier.language),
        encoding="utf-8",
    )
    verifier_path.chmod(0o755)

    if draft.solution and draft.solution.code.strip():
        sol_path = out_dir / "solution" / SOLUTION_NAME
        sol_path.write_text(
            render_solution_entry(
                draft.solution.code,
                draft.solution.language,
                draft.environment.workdir or "/app",
            ),
            encoding="utf-8",
        )
        sol_path.chmod(0o755)

    meta = {
        "name": draft.name,
        "description": draft.description,
        "source_notes": draft.source_notes,
        "metadata": draft.metadata.model_dump(),
        "reward_floor": draft.reward_floor,
        "staged_assets": present,
        "missing_assets": missing,
        "recipes": detect_recipes(
            draft.source_notes + chr(10) + draft.instruction_md
        ),
    }
    (out_dir / "envwiki.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + NL, encoding="utf-8"
    )
    return out_dir
