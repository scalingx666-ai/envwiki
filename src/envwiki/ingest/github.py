"""Clone GitHub repositories and distil them into text context."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from envwiki.ingest.classify import GitHubRef

#: Files worth showing to the model verbatim.
KEY_FILES = (
    "README.md",
    "README.rst",
    "README.txt",
    "readme.md",
    "readme.en.md",
    "readme.zh.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "tsconfig.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "LICENSE",
)

#: Directory names never worth walking into.
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".idea",
    ".vscode", "vendor", "third_party", ".next", ".cache", "site-packages",
}

MAX_TREE_ENTRIES = 400
MAX_FILE_CHARS = 12_000
MAX_INDEX_FILES = 200
MAX_HEADINGS = 40
MAX_HEADING_SCAN_CHARS = 2_000_000
TEXT_SUFFIXES = {
    ".md", ".markdown", ".rst", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".sh", ".bash", ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".java", ".rb",
    ".php", ".swift", ".kt", ".scala", ".lua", ".sql", ".csv", ".tsv", ".toml",
    ".yaml", ".yml", ".json", ".cfg", ".ini", ".html", ".htm",
}

NL = chr(10)


@dataclass(slots=True)
class CloneResult:
    path: Path
    ref: GitHubRef
    ok: bool
    error: str = ""


def clone_github_repo(
    ref: GitHubRef,
    dest: Path,
    *,
    depth: int = 1,
    timeout: int = 300,
) -> CloneResult:
    """Shallow-clone a repository into dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth", str(depth), "--single-branch"]
    if ref.ref and ref.kind != "gist":
        cmd += ["--branch", ref.ref]
    cmd += [ref.clone_url, str(dest)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return CloneResult(dest, ref, False, "git executable not found")
    except subprocess.TimeoutExpired:
        return CloneResult(dest, ref, False, f"git clone timed out after {timeout}s")
    if proc.returncode != 0:
        return CloneResult(dest, ref, False, (proc.stderr or proc.stdout).strip()[:500])
    return CloneResult(dest, ref, True)


def _iter_files(root: Path, limit: int = MAX_TREE_ENTRIES) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if len(out) >= limit:
            break
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and not path.name.startswith("."):
            out.append(path)
    return out


def _headings(text: str) -> list[str]:
    """Markdown-style headings with their line numbers."""
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            found.append(str(number) + ": " + stripped[:120])
        if len(found) >= MAX_HEADINGS:
            break
    return found


def _text_index(path: Path) -> tuple[int, list[str]]:
    """(line count, headings) for a text file, best effort."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, []
    lines = text.count(NL) + 1
    if len(text) > MAX_HEADING_SCAN_CHARS:
        return lines, []
    return lines, _headings(text)


def build_index(root: Path, files: list[Path]) -> str:
    """A searchable index of the repository.

    The harness may only have read access, so it needs to know where things
    are without shelling out: every text file gets its size, its line count
    and its headings with line numbers.
    """
    lines: list[str] = []
    for path in files[:MAX_INDEX_FILES]:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        rel = path.relative_to(root)
        if path.suffix.lower() not in TEXT_SUFFIXES:
            lines.append("- " + str(rel) + " (" + str(size) + "B)")
            continue
        count, headings = _text_index(path)
        entry = "- " + str(rel) + " (" + str(size) + "B, " + str(count) + " lines)"
        if headings:
            lines.append(entry)
            for heading in headings:
                lines.append("    " + heading)
        else:
            lines.append(entry)
    if len(files) > MAX_INDEX_FILES:
        lines.append("- ... " + str(len(files) - MAX_INDEX_FILES) + " more files")
    return NL.join(lines)


def summarize_repo(root: Path, ref: GitHubRef | None = None) -> tuple[str, list[str]]:
    """Return (markdown context, relative file paths) for a cloned repository."""
    files = _iter_files(root)
    rel_paths = [str(p.relative_to(root)) for p in files]

    tree_lines: list[str] = []
    for p in files:
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        tree_lines.append(str(p.relative_to(root)) + " (" + str(size) + "B)")
    tree = NL.join(tree_lines) if tree_lines else "(empty)"

    parts: list[str] = []
    title = ref.slug if ref else root.name
    parts.append("# Repository: " + title)
    parts.append(NL + "Local path: " + str(root) + NL)
    parts.append("## File tree" + NL)
    parts.append(tree)
    parts.append(NL + "## Index" + NL)
    parts.append(build_index(root, files))

    for p in files:
        if p.name not in KEY_FILES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.strip():
            continue
        parts.append(NL + "## File: " + str(p.relative_to(root)) + NL)
        parts.append(text[:MAX_FILE_CHARS])

    return NL.join(parts), rel_paths
