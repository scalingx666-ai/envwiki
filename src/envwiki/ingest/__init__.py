"""Source ingestion: links in, staged material out."""

from envwiki.ingest.bundle import Bundle, build_bundle
from envwiki.ingest.classify import classify_url, parse_github_url
from envwiki.ingest.github import clone_github_repo, summarize_repo
from envwiki.ingest.reader import read_url
from envwiki.ingest.uploads import ingest_uploads

__all__ = [
    "Bundle",
    "build_bundle",
    "classify_url",
    "parse_github_url",
    "clone_github_repo",
    "summarize_repo",
    "read_url",
    "ingest_uploads",
]
