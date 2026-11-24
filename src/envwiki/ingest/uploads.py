#"""Parse uploaded files, including images, into usable context."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from envwiki.ingest.reader import html_to_text, read_local_document
from envwiki.schemas import IngestedSource, SourceKind

TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".text", ".rst", ".json", ".jsonl", ".yaml",
    ".yml", ".toml", ".ini", ".cfg", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".sh", ".bash", ".zsh", ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".java",
    ".rb", ".php", ".swift", ".kt", ".scala", ".lua", ".sql", ".csv", ".tsv",
    ".env", ".gradle", ".xml", ".html", ".htm",
}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}


@dataclass(slots=True)
class UploadResult:
    source: IngestedSource
    text: str
    image_paths: list[Path]


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:120]


def ingest_uploads(paths: list[Path], dest: Path) -> list[UploadResult]:
    """Copy uploads into the staging area and extract whatever text they hold."""
    dest.mkdir(parents=True, exist_ok=True)
    results: list[UploadResult] = []

    for raw in paths:
        src = raw.expanduser()
        if not src.exists() or not src.is_file():
            continue
        target = dest / _safe_name(src.name)
        if target.exists():
            target = dest / f"{target.stem}-{abs(hash(src)) % 9999}{target.suffix}"
        shutil.copy2(src, target)

        suffix = src.suffix.lower()
        text = ""
        images: list[Path] = []

        if suffix in IMAGE_SUFFIXES:
            images = [target]
            text = (
                "Image file: " + src.name + " (staged at " + str(target) + "). "
                "Read that path to see the image; it is part of the task material."
            )
        elif suffix == ".pdf":
            text, strategy = read_local_document(target)
            text = f"## Document: {src.name}\n\n(text extracted via {strategy})\n\n{text}"
        elif suffix in {".html", ".htm"}:
            body = html_to_text(target.read_text(encoding="utf-8", errors="replace"))
            text = "## Document: " + src.name + chr(10) * 2 + body
        elif suffix in TEXT_SUFFIXES:
            body = target.read_text(encoding="utf-8", errors="replace")
            text = f"## Document: {src.name}\n\n{body}"
        else:
            raw_text, _ = read_local_document(target)
            if raw_text.strip():
                text = f"## Document: {src.name}\n\n{raw_text}"
            else:
                text = f"Binary upload: {src.name} ({target.stat().st_size} bytes)."

        results.append(
            UploadResult(
                source=IngestedSource(
                    kind=SourceKind.UPLOAD,
                    name=src.name,
                    origin=str(src),
                    location=str(target),
                    summary=text[:300].replace("\n", " "),
                    files=[str(target)],
                    image_paths=[str(p) for p in images],
                ),
                text=text,
                image_paths=images,
            )
        )

    return results
