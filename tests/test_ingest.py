"""Tests for link classification and ingestion."""

from __future__ import annotations

from pathlib import Path

from envwiki.ingest.bundle import build_bundle, build_tree, sanitize_staged_roots
from envwiki.ingest.classify import classify_url, parse_github_url
from envwiki.schemas import SourceKind


def test_classify_github_and_web():
    assert classify_url("https://github.com/a/b") is SourceKind.GITHUB
    assert classify_url("https://gist.github.com/a/b") is SourceKind.GITHUB
    assert classify_url("https://raw.githubusercontent.com/a/b/main/x.py") is SourceKind.GITHUB
    assert classify_url("https://example.com/x") is SourceKind.WEB
    assert classify_url("example.com/x") is SourceKind.WEB


def test_parse_repo_url_with_s_in_owner():
    # A character class of [^/s] would reject owners containing an "s".
    ref = parse_github_url("https://github.com/scalingx666-ai/awesome-environment")
    assert ref is not None
    assert ref.owner == "scalingx666-ai"
    assert ref.repo == "awesome-environment"
    assert ref.kind == "repo"
    assert ref.clone_url == "https://github.com/scalingx666-ai/awesome-environment.git"


def test_parse_tree_and_blob_urls():
    tree = parse_github_url("https://github.com/o/r/tree/main/src")
    assert tree is not None and tree.kind == "tree"
    assert tree.ref == "main" and tree.path == "src"

    blob = parse_github_url("https://github.com/o/r/blob/main/src/x.py")
    assert blob is not None and blob.kind == "blob"
    assert blob.ref == "main" and blob.path == "src/x.py"

    raw = parse_github_url("https://raw.githubusercontent.com/o/r/main/src/x.py")
    assert raw is not None and raw.kind == "blob"
    assert raw.raw_url is not None


def test_parse_gist_url():
    ref = parse_github_url("https://gist.github.com/someone/abc123")
    assert ref is not None
    assert ref.kind == "gist"
    assert ref.clone_url.endswith(".git")


def test_parse_non_github_returns_none():
    assert parse_github_url("https://example.com/page") is None


def test_build_bundle_stages_uploads(tmp_path: Path):
    upload = tmp_path / "notes.md"
    upload.write_text("hello notes", encoding="utf-8")

    staging = tmp_path / "workspace"
    bundle = build_bundle([], [upload], staging)

    assert bundle.ok
    assert bundle.sources[0].kind is SourceKind.UPLOAD
    assert "hello notes" in bundle.digest
    assert (staging / "uploads" / "notes.md").is_file()
    assert "uploads/notes.md" in bundle.tree


def test_build_bundle_clears_previous_staging(tmp_path: Path):
    staging = tmp_path / "workspace"
    staging.mkdir()
    (staging / "stale.txt").write_text("old", encoding="utf-8")

    bundle = build_bundle([], [], staging)
    assert not (staging / "stale.txt").exists()
    assert bundle.sources == []


def test_sanitize_removes_pi_resource_dirs(tmp_path: Path):
    root = tmp_path / "repo"
    (root / ".pi" / "extensions").mkdir(parents=True)
    (root / ".pi" / "extensions" / "evil.ts").write_text("x", encoding="utf-8")
    (root / ".agents" / "skills").mkdir(parents=True)
    (root / "keep.md").write_text("keep", encoding="utf-8")

    removed = sanitize_staged_roots(root)

    assert not (root / ".pi").exists()
    assert not (root / ".agents").exists()
    assert (root / "keep.md").exists()
    assert len(removed) == 2


def test_build_tree_skips_noise(tmp_path: Path):
    (tmp_path / ".pi").mkdir()
    (tmp_path / ".pi" / "mcp.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    tree = build_tree(tmp_path)
    assert "a.txt" in tree
    assert "mcp.json" not in tree
