"""Typed shapes shared across ingest, scaffolding and validation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SourceKind(StrEnum):
    GITHUB = "github"
    WEB = "web"
    UPLOAD = "upload"


class IngestedSource(BaseModel):
    """One resolved input: a cloned repo, a fetched page, or an upload."""
    kind: SourceKind
    name: str
    origin: str
    location: str
    summary: str = ""
    files: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)

    def brief(self) -> str:
        head = f"{self.kind}: {self.name}"
        return f"{head} ({self.origin})" if self.origin else head


class Provenance(BaseModel):
    """Where the task's material came from, pinned so it can be reproduced.

    ScienceIDE's rule: a task runs on an unmodified, pinned upstream. A
    commit hash and a content hash are what make "the same task" a
    checkable claim instead of a story.
    """
    upstream_repo: str = ""
    upstream_commit: str = ""
    upstream_license: str = ""
    source_archive_sha256: str = ""
    derived_from: str = ""

    @property
    def pinned(self) -> bool:
        """True when the material is pinned well enough to rebuild it."""
        return bool(self.upstream_commit) and bool(self.upstream_repo)


class TaskMetadata(BaseModel):
    """What the task says about itself.

    Difficulty is not a label the author picks: it is "unrated" until a
    measurement exists. The facts a measurement produces live in
    difficulty_facts, so a reader can always tell an opinion from a
    measurement.
    """
    difficulty: str = "unrated"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)
    difficulty_facts: dict[str, object] = Field(default_factory=dict)

    @field_validator("difficulty")
    @classmethod
    def _known_difficulty(cls, v: str) -> str:
        v = (v or "unrated").strip().lower()
        if v in {"easy", "medium", "hard"}:
            # A hand-written tier is allowed but is never a measurement.
            return v
        return v if v in {"unrated", "unknown"} else "unrated"


class EnvironmentSpec(BaseModel):
    """How the Harbor environment is built."""
    base_image: str = "ubuntu:24.04"
    workdir: str = "/app"
    os: str = "linux"
    setup_commands: list[str] = Field(default_factory=list)
    copy_from_staging: list[str] = Field(default_factory=list)


class VerifierSpec(BaseModel):
    """The test that produces the reward.

    The verifier runs as tests/test.sh: Harbor only discovers test.sh or
    test.bat, and only that one file is uploaded into the container. A
    verifier written in another language therefore has to be reachable
    from that single entry point.
    """
    language: str = "bash"
    code: str
    timeout_sec: float = 900.0

    @field_validator("language")
    @classmethod
    def _known_lang(cls, v: str) -> str:
        v = (v or "bash").strip().lower()
        return v if v in {"bash", "python"} else "bash"


class SolutionSpec(BaseModel):
    """The reference solution that should make the verifier pass.

    It runs as solution/solve.sh, for the same reason the verifier runs
    as test.sh: Harbor discovers and uploads one file per directory.
    """
    language: str = "bash"
    code: str

    @field_validator("language")
    @classmethod
    def _known_lang(cls, v: str) -> str:
        v = (v or "bash").strip().lower()
        return v if v in {"bash", "python"} else "bash"


class TaskDraft(BaseModel):
    """The shape of a task, as scaffold_task takes it.

    One draft becomes one Harbor task directory. The tool signature of
    scaffold_task and this model are the same contract: there is no second
    description of a task anywhere else.
    """
    name: str = "envwiki-task"
    description: str = ""
    metadata: TaskMetadata = Field(default_factory=TaskMetadata)
    instruction_md: str
    environment: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    verifier: VerifierSpec
    solution: SolutionSpec | None = None
    source_notes: str = ""
    reward_floor: float | None = None

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = (v or "").strip().lower()
        v = "".join(c if c.isalnum() or c in "-_" else "-" for c in v)
        v = "-".join(part for part in v.split("-") if part)
        return v or "envwiki-task"
