"""Validate a generated task directory against Harbor's expectations.

Harbor's own TaskConfig model is used when it can be imported; otherwise a
local structural check runs so envwiki still works without a Harbor install.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ORG_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*/[a-zA-Z0-9][a-zA-Z0-9._-]*$")
SUPPORTED_SCHEMA_VERSION = "1.4"
REWARD_MARKER = "/logs/verifier/reward"
DIFFICULTIES = {"easy", "medium", "hard"}
TASK_OS = {"linux", "windows"}


@dataclass
class Issue:
    level: str
    message: str


@dataclass
class ValidationReport:
    task_dir: str
    issues: list[Issue] = field(default_factory=list)
    schema_source: str = "local"

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


def _harbor_candidates() -> list[Path]:
    here = Path(__file__).resolve()
    project_root = here.parents[3]
    candidates: list[Path] = []
    env_src = os.environ.get("HARBOR_SRC")
    if env_src:
        candidates.append(Path(env_src).expanduser())
    candidates.append(project_root.parent / "harbor" / "src")
    candidates.append(project_root / "harbor" / "src")
    return candidates


def _harbor_version(src_dir: Path) -> str:
    pyproject = src_dir.parent / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str((data.get("project") or {}).get("version") or "0.0.0")
    except Exception:
        return "0.0.0"


def _install_metadata_shim(src_dir: Path) -> None:
    """Give an uninstalled Harbor checkout its package metadata.

    harbor/__init__.py asks importlib.metadata for its own version, which
    fails when Harbor is used straight from a source checkout.
    """
    version = _harbor_version(src_dir)
    tmp = tempfile.mkdtemp(prefix="envwiki-harbor-")
    dist_info = Path(tmp) / ("harbor-" + version + ".dist-info")
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1" + chr(10)
        + "Name: harbor" + chr(10)
        + "Version: " + version + chr(10),
        encoding="utf-8",
    )
    sys.path.insert(0, tmp)


def _purge_harbor_modules() -> None:
    for name in [n for n in list(sys.modules) if n == "harbor" or n.startswith("harbor.")]:
        del sys.modules[name]


def load_harbor_task_config():
    """Return Harbor's TaskConfig class, or None when Harbor is unavailable."""
    try:
        module = importlib.import_module("harbor.models.task.config")
        return getattr(module, "TaskConfig", None)
    except Exception:
        pass

    for candidate in _harbor_candidates():
        if not candidate.is_dir():
            continue
        entry = str(candidate)
        if entry not in sys.path:
            sys.path.insert(0, entry)
        _install_metadata_shim(candidate)
        importlib.invalidate_caches()
        try:
            module = importlib.import_module("harbor.models.task.config")
            return getattr(module, "TaskConfig", None)
        except Exception:
            _purge_harbor_modules()
            continue
    return None


def _copy_sources(dockerfile: str) -> list[str]:
    """The files a Dockerfile copies, relative to the build context."""
    sources: list[str] = []
    for line in dockerfile.splitlines():
        parts = line.strip().split()
        if len(parts) < 3 or parts[0].upper() != "COPY":
            continue
        if any(part.startswith("--") for part in parts):
            continue
        for source in parts[1:-1]:
            if source and not source.endswith("/"):
                sources.append(source)
    return sources


def _check_files(task_dir: Path, issues: list[Issue]) -> None:
    instruction = task_dir / "instruction.md"
    if not instruction.exists():
        issues.append(Issue("error", "missing instruction.md"))
    elif not instruction.read_text(encoding="utf-8").strip():
        issues.append(Issue("error", "instruction.md is empty"))

    dockerfile = task_dir / "environment" / "Dockerfile"
    if dockerfile.exists():
        body = dockerfile.read_text(encoding="utf-8")
        if "FROM " not in body.upper():
            issues.append(Issue("error", "environment/Dockerfile has no FROM instruction"))
        for source in _copy_sources(body):
            if not (task_dir / "environment" / source).exists():
                issues.append(
                    Issue(
                        "error",
                        "Dockerfile copies '"
                        + source
                        + "', which is not in the build context",
                    )
                )
    else:
        issues.append(Issue("warning", "no environment/Dockerfile"))

    tests_dir = task_dir / "tests"
    verifier_files = list(tests_dir.glob("test.*")) if tests_dir.is_dir() else []
    if not verifier_files:
        issues.append(Issue("error", "no verifier found in tests/"))
    else:
        verifier = verifier_files[0]
        code = verifier.read_text(encoding="utf-8")
        if not code.strip():
            issues.append(Issue("error", "verifier " + verifier.name + " is empty"))
        if REWARD_MARKER not in code:
            issues.append(Issue("error", "verifier does not write " + REWARD_MARKER + ".txt"))
        if verifier.suffix == ".sh" and not verifier.stat().st_mode & 0o111:
            issues.append(Issue("warning", "verifier " + verifier.name + " is not executable"))

    solution_dir = task_dir / "solution"
    solution_files = list(solution_dir.glob("solve.*")) if solution_dir.is_dir() else []
    if not solution_files:
        issues.append(Issue("warning", "no reference solution in solution/"))


def validate_task(task_dir: Path) -> ValidationReport:
    """Check a task directory; returns every problem found."""
    task_dir = Path(task_dir).expanduser().resolve()
    report = ValidationReport(task_dir=str(task_dir))
    issues = report.issues

    if not task_dir.is_dir():
        issues.append(Issue("error", "task directory does not exist: " + str(task_dir)))
        return report

    toml_path = task_dir / "task.toml"
    data: dict | None = None
    if not toml_path.exists():
        issues.append(Issue("error", "missing task.toml"))
    else:
        try:
            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append(Issue("error", "task.toml is not valid TOML: " + str(exc)))

    if data is not None:
        version = str(data.get("schema_version") or data.get("version") or "")
        if not version:
            issues.append(Issue("error", "task.toml has no schema_version"))
        elif version != SUPPORTED_SCHEMA_VERSION:
            issues.append(
                Issue(
                    "warning",
                    "schema_version "
                    + repr(version)
                    + " differs from Harbor's "
                    + SUPPORTED_SCHEMA_VERSION,
                )
            )

        task = data.get("task") or {}
        name = str(task.get("name") or "")
        if name and not ORG_NAME_PATTERN.match(name):
            issues.append(
                Issue("error", "[task].name " + repr(name) + " must be in org/name format")
            )

        metadata = data.get("metadata") or {}
        difficulty = str(metadata.get("difficulty") or "")
        if difficulty and difficulty not in DIFFICULTIES:
            issues.append(Issue("warning", "unknown difficulty: " + repr(difficulty)))

        environment = data.get("environment") or {}
        os_name = str(environment.get("os") or "linux")
        if os_name not in TASK_OS:
            issues.append(Issue("error", "unsupported environment.os: " + repr(os_name)))

        verifier_cfg = data.get("verifier") or {}
        timeout = verifier_cfg.get("timeout_sec")
        if timeout is None:
            issues.append(Issue("warning", "[verifier].timeout_sec is not set"))
        elif float(timeout) <= 0:
            issues.append(Issue("error", "[verifier].timeout_sec must be positive"))

    _check_files(task_dir, issues)

    task_config_cls = load_harbor_task_config()
    if task_config_cls is not None and data is not None:
        report.schema_source = "harbor"
        try:
            task_config_cls.model_validate(data)
        except Exception as exc:
            issues.append(Issue("error", "Harbor TaskConfig rejected task.toml: " + str(exc)[:400]))

    return report
