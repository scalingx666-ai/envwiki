"""Data model for synthesis recipes.

A recipe is one environment/task synthesis method, abstracted from the
papers that describe it, so that an agent harness can follow it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Effort = Literal["low", "medium", "high"]


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


class Recipe(BaseModel):
    """One abstract synthesis method."""

    id: str
    name: str
    family: str
    summary: str = ""
    when_to_use: list[str] = Field(default_factory=list)
    not_when_to_use: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    steps: list[RecipeStep] = Field(default_factory=list)
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
        parts = [self.id, self.name, self.family, self.summary]
        parts.extend(self.when_to_use)
        parts.extend(self.inputs)
        for step in self.steps:
            parts.append(step.title)
            parts.append(step.detail)
        parts.extend(self.verifier)
        parts.extend(self.pitfalls)
        return " ".join(parts)
