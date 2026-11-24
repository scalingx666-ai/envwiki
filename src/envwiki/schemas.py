"""Typed shapes shared across ingest, harness and conversion."""

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


class TaskMetadata(BaseModel):
    difficulty: str = "medium"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)

    @field_validator("difficulty")
    @classmethod
    def _known_difficulty(cls, v: str) -> str:
        v = (v or "medium").strip().lower()
        return v if v in {"easy", "medium", "hard"} else "medium"


class EnvironmentSpec(BaseModel):
    """How the Harbor environment is built."""

    base_image: str = "ubuntu:24.04"
    workdir: str = "/app"
    os: str = "linux"
    setup_commands: list[str] = Field(default_factory=list)
    copy_from_staging: list[str] = Field(default_factory=list)


class VerifierSpec(BaseModel):
    """The test that produces the reward."""

    language: str = "bash"
    code: str
    timeout_sec: float = 900.0

    @field_validator("language")
    @classmethod
    def _known_lang(cls, v: str) -> str:
        v = (v or "bash").strip().lower()
        return v if v in {"bash", "python"} else "bash"


class SolutionSpec(BaseModel):
    """The reference solution that should make the verifier pass."""

    language: str = "bash"
    code: str

    @field_validator("language")
    @classmethod
    def _known_lang(cls, v: str) -> str:
        v = (v or "bash").strip().lower()
        return v if v in {"bash", "python"} else "bash"


class TaskDraft(BaseModel):
    """The intermediate representation the model produces.

    One draft becomes one Harbor task directory.
    """

    name: str = "envwiki-task"
    description: str = ""
    metadata: TaskMetadata = Field(default_factory=TaskMetadata)
    instruction_md: str
    environment: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    verifier: VerifierSpec
    solution: SolutionSpec | None = None
    source_notes: str = ""

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = (v or "").strip().lower()
        v = "".join(c if c.isalnum() or c in "-_" else "-" for c in v)
        v = "-".join(part for part in v.split("-") if part)
        return v or "envwiki-task"


class BuildResult(BaseModel):
    """Outcome of one envwiki build."""

    task_dir: str
    draft: TaskDraft
    sources: list[IngestedSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    harness: str = "pi"
    model: str = ""
