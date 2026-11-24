"""Decide what kind of source a link points at."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from envwiki.schemas import SourceKind

GITHUB_HOSTS = {"github.com", "www.github.com", "gist.github.com", "raw.githubusercontent.com"}


@dataclass(slots=True)
class GitHubRef:
    """A parsed GitHub URL."""

    owner: str
    repo: str
    kind: str = "repo"  # repo | tree | blob | gist
    ref: str | None = None
    path: str | None = None
    raw_url: str | None = None

    @property
    def slug(self) -> str:
        return f"{self.owner}-{self.repo}"

    @property
    def clone_url(self) -> str:
        if self.kind == "gist":
            return f"https://gist.github.com/{self.owner}.git"
        return f"https://github.com/{self.owner}/{self.repo}.git"


def classify_url(url: str) -> SourceKind:
    """Return the ingestion strategy for a URL."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or "").lower().split(":")[0]
    if host in GITHUB_HOSTS:
        return SourceKind.GITHUB
    if host.endswith("githubusercontent.com"):
        return SourceKind.GITHUB
    return SourceKind.WEB


_GITHUB_RE = re.compile(
    r"^(?:https?://)?(?:www.)?github.com/"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)"
    r"(?:/(?P<kind>tree|blob)/(?P<ref>[^/\s]+)(?:/(?P<path>[^\s]+))?)?"
    r"/?$",
    re.IGNORECASE,
)

_GIST_RE = re.compile(
    r"^(?:https?://)?(?:www.)?gist.github.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/?$",
    re.IGNORECASE,
)

_RAW_RE = re.compile(
    r"^(?:https?://)?raw.githubusercontent.com/"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/(?P<ref>[^/\s]+)/(?P<path>.+)$",
    re.IGNORECASE,
)


def parse_github_url(url: str) -> GitHubRef | None:
    """Parse a GitHub URL into its parts, or None if it is not one."""
    url = url.strip()
    m = _GIST_RE.match(url)
    if m:
        return GitHubRef(owner=m.group("owner"), repo=m.group("repo"), kind="gist")

    m = _RAW_RE.match(url)
    if m:
        return GitHubRef(
            owner=m.group("owner"),
            repo=m.group("repo"),
            kind="blob",
            ref=m.group("ref"),
            path=m.group("path"),
            raw_url=url if "://" in url else f"https://{url}",
        )

    m = _GITHUB_RE.match(url)
    if not m:
        return None
    repo = m.group("repo")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return GitHubRef(
        owner=m.group("owner"),
        repo=repo,
        kind=(m.group("kind") or "repo").lower(),
        ref=m.group("ref"),
        path=m.group("path"),
    )
