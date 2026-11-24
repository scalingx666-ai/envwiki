"""Turn a TaskDraft into a Harbor task directory."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from envwiki.recipes import load_library
from envwiki.schemas import TaskDraft

SOLUTION_NAMES = {"bash": "solve.sh", "python": "solve.py"}
VERIFIER_NAMES = {"bash": "test.sh", "python": "test.py"}
DEFAULT_ORG = "envwiki"

NL = chr(10)

#: The file that marks a directory as a Harbor task.
TASK_FILE = "task.toml"

#: Staged source directories: a task is never found inside the material.
SOURCE_DIRS = {"repos", "pages", "uploads"}


def _toml_str(value: str) -> str:
    """Quote a value as a TOML basic string (JSON escaping is TOML-compatible)."""
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: list[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


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

    lines.append("[verifier]")
    lines.append(f"timeout_sec = {float(draft.verifier.timeout_sec)}")
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


def render_dockerfile(draft: TaskDraft, destinations: dict[str, str] | None = None) -> str:
    """Render environment/Dockerfile (the Docker build context is environment/)."""
    env = draft.environment
    workdir = env.workdir or "/app"
    if destinations is None:
        destinations = asset_destinations(draft)
    parts: list[str] = [f"FROM {env.base_image}", ""]

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
    """Materialise a Harbor task directory and return its path."""
    out_dir = out_dir.expanduser().resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for sub in ("environment", "solution", "tests"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    destinations = asset_destinations(draft)
    copied = _copy_staged_assets(draft, out_dir, staging_dir, destinations)
    if copied:
        draft.environment.copy_from_staging = copied

    (out_dir / "task.toml").write_text(
        render_task_toml(draft, org=org, author=author), encoding="utf-8"
    )
    (out_dir / "instruction.md").write_text(
        draft.instruction_md.strip() + NL, encoding="utf-8"
    )
    (out_dir / "environment" / "Dockerfile").write_text(
        render_dockerfile(draft, destinations), encoding="utf-8"
    )

    verifier_lang = draft.verifier.language
    verifier_code = _ensure_reward_write(draft.verifier.code, verifier_lang)
    verifier_path = out_dir / "tests" / VERIFIER_NAMES[verifier_lang]
    verifier_path.write_text(verifier_code, encoding="utf-8")
    verifier_path.chmod(0o755)

    if draft.solution and draft.solution.code.strip():
        sol_lang = draft.solution.language
        sol_path = out_dir / "solution" / SOLUTION_NAMES[sol_lang]
        sol_path.write_text(draft.solution.code, encoding="utf-8")
        sol_path.chmod(0o755)

    meta = {
        "name": draft.name,
        "description": draft.description,
        "source_notes": draft.source_notes,
        "metadata": draft.metadata.model_dump(),
        "staged_assets": destinations,
        "recipes": detect_recipes(
            draft.source_notes + chr(10) + draft.instruction_md
        ),
    }
    (out_dir / "envwiki.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + NL, encoding="utf-8"
    )
    return out_dir


def discover_tasks(root: Path) -> list[Path]:
    """Every task directory the agent produced under root.

    The agent writes through the scaffolding tool, so the task shows up as a
    directory that holds a task.toml. Anything inside the staged material is
    ignored: the source is data, not a task.
    """
    root = Path(root).expanduser().resolve()
    found: list[Path] = []

    def add(path: Path) -> None:
        if path not in found:
            found.append(path)

    if (root / TASK_FILE).is_file():
        add(root)

    tasks_root = root / "tasks"
    if tasks_root.is_dir():
        for child in sorted(tasks_root.iterdir()):
            if (child / TASK_FILE).is_file():
                add(child)

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".")
            and name not in SOURCE_DIRS
            and name != "node_modules"
        ]
        if TASK_FILE in filenames:
            add(Path(dirpath))

    return found


def publish_task(task_dir: Path, out_root: Path) -> Path:
    """Copy a finished task directory under out_root and return the copy."""
    task_dir = Path(task_dir).expanduser().resolve()
    out_root = Path(out_root).expanduser().resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    target = out_root / task_dir.name
    if target == task_dir:
        return task_dir
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(task_dir, target)
    return target
