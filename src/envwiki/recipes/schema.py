"""Data model for synthesis recipes.

A recipe is one environment/task synthesis method, abstracted from the
papers that describe it, so that an agent harness can follow it.

The shape is deliberately split in two:

- the **card** is what an agent compares: a short summary, the kind of
  material the method works on, the kind of task it poses, what it needs
  and what it produces. Cards are cheap to read and compare.
- the **procedure** is what an agent follows: the steps, each with the
  condition that says the step worked.

Steps that only matter when you build a whole set of tasks, rather than
one task, live in curation_notes. They are kept, because they carry
real advice, but they are not part of the procedure an agent follows.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Effort = Literal["low", "medium", "high"]

#: The kind of source material a method works on.
MaterialKind = Literal[
    "code",           # a repository or a program
    "web",            # a web page or a browser application
    "gui",            # a desktop or native application
    "api",            # a service or a set of tools
    "data",           # a dataset or a data pipeline
    "simulation",     # a simulated world or a world model
    "multi-agent",    # several agents acting on each other
    "embodied",       # a physical or spatial world
    "trajectory",     # traces of what someone already did
    "specification",  # a specification, with nothing to execute yet
    "paper",           # a research paper: prose, with nothing executable
    "infrastructure", # a platform, a sandbox or a harness
]

#: The kind of gap a task poses for the solver.
TaskKind = Literal[
    "implement",   # build what the specification describes
    "repair",      # fix something that is broken
    "reverse",     # recover the implementation from its behaviour
    "optimize",    # make something meet a bound
    "extend",      # add behaviour to something that works
    "reproduce",   # reproduce a known outcome exactly
    "none",        # the method produces no solver-facing task
]

#: What the method is for.
#:
#: - create: the solver gets a task to solve.
#: - environment: the method only builds a runnable environment; it poses
#:   no solver-facing task on its own.
#: - verify: the method produces a checker or a measurement.
#: - curate: the method produces a set of tasks or a curriculum.
RecipeRole = Literal["create", "environment", "verify", "curate"]


class SourcePaper(BaseModel):
    """A paper the recipe is grounded in."""

    arxiv_id: str
    title: str = ""
    note: str = ""

    @field_validator("arxiv_id")
    @classmethod
    def _normalise(cls, v: str) -> str:
        return (v or "").strip().lower()


class RecipeStep(BaseModel):
    """One step of the synthesis procedure."""

    title: str
    detail: str = ""
    #: What has to be true for the step to count as done.
    accept: str = ""


class Recipe(BaseModel):
    """One abstract synthesis method."""

    id: str
    name: str
    family: str
    #: One or two sentences: what the method does, in the agent's terms.
    summary: str = ""
    #: The longer distillation, kept for retrieval and for get_recipe.
    background: str = ""
    #: What kind of material this method works on.
    material_kind: list[MaterialKind] = Field(default_factory=list)
    #: What kind of gap this method poses for the solver.
    task_kind: TaskKind = "implement"
    #: Whether the method makes a task, checks one, or curates a set.
    role: RecipeRole = "create"
    #: What the method needs from the material, as short labels.
    needs: list[str] = Field(default_factory=list)
    #: What the solver ends up with.
    produces: str = ""
    when_to_use: list[str] = Field(default_factory=list)
    not_when_to_use: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    steps: list[RecipeStep] = Field(default_factory=list)
    #: Advice that matters when building a set of tasks, not one task.
    curation_notes: list[str] = Field(default_factory=list)
    verifier: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    effort: Effort = "medium"
    source_papers: list[SourcePaper] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v.replace("_", "-").replace(" ", "-")

    def summary_line(self) -> str:
        return self.id + " | " + self.name + " | " + self.family + " | " + self.summary[:160]

    def searchable_text(self) -> str:
        parts = [self.id, self.name, self.family, self.summary, self.background]
        parts.extend(self.material_kind)
        parts.extend(self.needs)
        parts.append(self.produces)
        parts.extend(self.when_to_use)
        parts.extend(self.inputs)
        for step in self.steps:
            parts.append(step.title)
            parts.append(step.detail)
            parts.append(step.accept)
        parts.extend(self.verifier)
        parts.extend(self.pitfalls)
        return " ".join(parts)
