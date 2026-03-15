"""
Content extractor — strip HTML to readable text.

Tries BeautifulSoup first; falls back to regex-based extraction.
"""

import logging
import re

logger = logging.getLogger(__name__)

_MAX_TEXT_CHARS = 8000  # per-page cap


def extract(html: str, *, max_chars: int = _MAX_TEXT_CHARS) -> tuple[str, str]:
    """Return ``(title, body_text)`` from raw HTML.

    Body text is capped at *max_chars* characters.
    """
    if not html:
        return "", ""
    try:
        return _extract_bs4(html, max_chars)
    except Exception:
        return _extract_fallback(html, max_chars)


# ── BeautifulSoup path ──────────────────────────────────────────


def _extract_bs4(html: str, max_chars: int) -> tuple[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""

    # Remove noise elements
    for tag in soup.find_all(
        ["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "svg"]
    ):
        tag.decompose()

    # Locate main content region
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.find(id=lambda x: x and "content" in x.lower() if x else False)
        or soup.find(class_=lambda x: x and "content" in " ".join(x).lower() if x else False)
        or soup.body
        or soup
    )

    text = main.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text[:max_chars]


# ── Regex fallback ──────────────────────────────────────────────


def _extract_fallback(html: str, max_chars: int) -> tuple[str, str]:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for old, new in [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " "),
    ]:
        text = text.replace(old, new)
    return title, text[:max_chars]
