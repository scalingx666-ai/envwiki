"""Turn links and uploads into one staged workspace plus an inline digest."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from envwiki.ingest.classify import classify_url, parse_github_url
from envwiki.ingest.github import clone_github_repo, summarize_repo
from envwiki.ingest.reader import read_url
from envwiki.ingest.uploads import ingest_uploads
from envwiki.schemas import IngestedSource, SourceKind

NL = chr(10)

MAX_TREE_ENTRIES = 300
SKIP_TREE_DIRS = {
    ".pi",
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


@dataclass(slots=True)
class Bundle:
    """Material staged for the harness, plus a digest of it."""

    staging_dir: Path
    sources: list[IngestedSource] = field(default_factory=list)
    digest: str = ""
    tree: str = ""
    images: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.sources)


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (text or "").strip())
    return cleaned.strip("-.") or "source"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _page_path(base: Path, name: str) -> Path:
    return base / (_slug(name) + ".md")


def build_tree(root: Path, limit: int = MAX_TREE_ENTRIES) -> str:
    """A readable listing of everything staged under root."""
    rows: list[str] = []
    for path in sorted(root.rglob("*")):
        if len(rows) >= limit:
            rows.append("... (truncated)")
            break
        rel = path.relative_to(root)
        if any(part in SKIP_TREE_DIRS for part in rel.parts):
            continue
        rows.append(str(rel) + ("/" if path.is_dir() else ""))
    return NL.join(rows) if rows else "(empty)"


def ingest_links(
    links: list[str], staging_dir: Path
) -> tuple[list[IngestedSource], list[str], list[str]]:
    """Resolve links into staged material.

    GitHub links are cloned; everything else is read through the reader.
    Returns (sources, warnings, text blocks).
    """
    sources: list[IngestedSource] = []
    warnings: list[str] = []
    texts: list[str] = []

    for raw in links:
        url = raw.strip()
        if not url:
            continue
        kind = classify_url(url)

        if kind is SourceKind.GITHUB:
            ref = parse_github_url(url)
            if ref is None:
                warnings.append("could not parse GitHub URL: " + url)
                continue
            dest = staging_dir / "repos" / _slug(ref.slug)
            clone = clone_github_repo(ref, dest)
            if clone.ok:
                context, files = summarize_repo(dest, ref)
                sources.append(
                    IngestedSource(
                        kind=SourceKind.GITHUB,
                        name=ref.slug,
                        origin=url,
                        location=str(dest),
                        summary=context[:300].replace(NL, " "),
                        files=files,
                    )
                )
                texts.append(context)
                continue

            warnings.append("clone failed for " + url + ": " + clone.error)
            fallback = read_url(url)
            if not fallback.ok:
                warnings.append("reader fallback failed for " + url + ": " + fallback.error)
                continue
            target = _page_path(staging_dir / "pages", ref.slug)
            _write_text(target, fallback.markdown)
            sources.append(
                IngestedSource(
                    kind=SourceKind.GITHUB,
                    name=ref.slug,
                    origin=url,
                    location=str(target),
                    summary=fallback.markdown[:300].replace(NL, " "),
                    files=[str(target)],
                )
            )
            texts.append("## Source: " + ref.slug + NL + fallback.markdown)
            continue

        result = read_url(url)
        if not result.ok:
            warnings.append("reader failed for " + url + ": " + result.error)
            continue
        name = _slug(result.title or url)
        target = _page_path(staging_dir / "pages", name)
        _write_text(target, result.markdown)
        sources.append(
            IngestedSource(
                kind=SourceKind.WEB,
                name=name,
                origin=url,
                location=str(target),
                summary=result.markdown[:300].replace(NL, " "),
                files=[str(target)],
            )
        )
        texts.append("## Source: " + name + NL + result.markdown)

    return sources, warnings, texts


UNTRUSTED_DIRS = {".pi", ".agents"}


def sanitize_staged_roots(root: Path) -> list[str]:
    """Strip project-local pi resource dirs out of the staged material.

    A cloned repository must never be able to register extensions, MCP
    servers or skills for the harness that explores it.
    """
    targets = [p for p in root.rglob("*") if p.is_dir() and p.name in UNTRUSTED_DIRS]
    removed: list[str] = []
    for path in sorted(targets, key=lambda p: len(p.parts), reverse=True):
        shutil.rmtree(path, ignore_errors=True)
        removed.append(str(path.relative_to(root)))
    return removed


def build_bundle(
    links: list[str],
    uploads: list[Path],
    staging_dir: Path,
    max_context_chars: int = 120_000,
) -> Bundle:
    """Ingest every input into a fresh staging directory."""
    staging_dir = Path(staging_dir).expanduser().resolve()
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    sources, warnings, texts = ingest_links(links, staging_dir)
    images: list[Path] = []

    if uploads:
        results = ingest_uploads(list(uploads), staging_dir / "uploads")
        for result in results:
            sources.append(result.source)
            texts.append(result.text)
            images.extend(result.image_paths)

    sanitize_staged_roots(staging_dir)

    digest = NL.join(texts)
    if len(digest) > max_context_chars:
        digest = digest[:max_context_chars] + NL + "... [digest truncated]"

    return Bundle(
        staging_dir=staging_dir,
        sources=sources,
        digest=digest,
        tree=build_tree(staging_dir),
        images=images,
        warnings=warnings,
    )
