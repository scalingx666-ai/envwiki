#"""Fetch and normalise arbitrary web pages into markdown."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

#: Jina Reader turns any URL into clean markdown.
JINA_READER_BASE = "https://r.jina.ai"

USER_AGENT = "envwiki/0.1 (+https://github.com/scalingx666-ai/awesome-environment)"

_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_RE = re.compile(r"\n{3,}")


@dataclass(slots=True)
class ReadResult:
    url: str
    title: str
    markdown: str
    ok: bool
    strategy: str = ""
    error: str = ""


def html_to_text(raw: str) -> str:
    """A dependency-free HTML to plain-text reduction."""
    raw = _SCRIPT_STYLE_RE.sub(" ", raw)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", raw, flags=re.IGNORECASE)
    raw = _TAG_RE.sub(" ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    raw = _BLANK_RE.sub("\n\n", raw)
    return raw.strip()


def _extract_title(raw_html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    return html.unescape(m.group(1)).strip()[:200]


def read_url(url: str, *, timeout: float = 60.0, use_jina: bool = True) -> ReadResult:
    """Read a URL with Jina Reader, falling back to a direct fetch."""
    errors: list[str] = []

    if use_jina:
        try:
            resp = httpx.get(
                f"{JINA_READER_BASE}/{url}",
                headers={"User-Agent": USER_AGENT, "Accept": "text/markdown"},
                timeout=timeout,
                follow_redirects=True,
            )
            if resp.status_code == 200 and resp.text.strip():
                body = resp.text.strip()
                title = body.splitlines()[0].lstrip("# ").strip()[:200] if body else ""
                return ReadResult(url, title, body, True, "jina-reader")
            errors.append(f"jina-reader HTTP {resp.status_code}")
        except Exception as exc:  # network failure should not be fatal
            errors.append(f"jina-reader: {type(exc).__name__}: {exc}")

    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        body = resp.text
        if "html" in ctype.lower() or body.lstrip()[:1] == "<":
            text = html_to_text(body)
            title = _extract_title(body)
        else:
            text = body
            title = ""
        if text.strip():
            return ReadResult(url, title, text.strip(), True, "direct-fetch")
        errors.append("direct fetch produced empty content")
    except Exception as exc:
        errors.append(f"direct-fetch: {type(exc).__name__}: {exc}")

    return ReadResult(url, "", "", False, "", "; ".join(errors)[:500])


def read_local_document(path: Path) -> tuple[str, str]:
    """Extract text from a local document. Returns (text, strategy)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = []
            for i, page in enumerate(reader.pages, 1):
                try:
                    pages.append(f"--- page {i} ---\n{page.extract_text() or ''}")
                except Exception:
                    continue
            text = "\n\n".join(pages)
            if text.strip():
                return text, "pypdf"
        except Exception:
            pass
        try:
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
            result = converter.convert(str(path))
            return result.document.export_to_markdown(), "docling"
        except Exception:
            return "", "unavailable"

    if suffix in {".html", ".htm"}:
        return html_to_text(path.read_text(encoding="utf-8", errors="replace")), "html"

    try:
        return path.read_text(encoding="utf-8", errors="replace"), "text"
    except OSError:
        return "", "unreadable"
