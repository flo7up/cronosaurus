"""
Function tool definitions for web search.

The agent can call these tools to search the web for current information,
look up facts, or find relevant web pages on any topic.

Uses DuckDuckGo as the search backend (no API key required).
"""

import json
import logging
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

# ── JSON-Schema definitions (OpenAI function-calling format) ────

WEB_SEARCH_TOOL_DEFINITIONS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for current information on any topic. "
            "Returns a list of relevant results with titles, URLs, and snippets. "
            "Use this when the user asks about recent events, facts you're unsure about, "
            "or anything that requires up-to-date information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query. Be specific and use keywords for best results. "
                        "For example: 'Python FastAPI tutorial 2025' or 'latest SpaceX launch'."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": (
                        "Maximum number of results to return. Defaults to 5. "
                        "Use fewer (2-3) for simple lookups, more (5-10) for research."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch and read the text content of a web page. "
            "Use this to read articles, blog posts, documentation, or any URL. "
            "Extracts the main readable content and strips navigation/ads. "
            "Returns the page title, extracted text, and metadata."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch, e.g. 'https://example.com/article'.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_scrape",
        "description": (
            "Scrape structured data from a web page. "
            "Can extract all links, headings, images, tables, or elements matching "
            "a CSS selector. Use this when you need specific structured data "
            "rather than just the page text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to scrape.",
                },
                "extract": {
                    "type": "string",
                    "description": (
                        "What to extract: 'links' (all links with text and href), "
                        "'headings' (h1-h6 structure), 'images' (img src and alt), "
                        "'tables' (table data as arrays), 'meta' (page metadata), "
                        "or a CSS selector like 'div.article p' or '#main-content'."
                    ),
                },
            },
            "required": ["url", "extract"],
        },
    },
]

WEB_SEARCH_TOOL_NAMES = {t["name"] for t in WEB_SEARCH_TOOL_DEFINITIONS}


# ── DuckDuckGo search helpers ───────────────────────────────────

def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """Search DuckDuckGo and return results using the HTML endpoint + lite parsing."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in results
        ]
    except ImportError:
        logger.warning("duckduckgo_search not installed, falling back to basic search")
        return _ddg_search_fallback(query, max_results)
    except Exception as e:
        logger.error("DuckDuckGo search error: %s", e)
        return _ddg_search_fallback(query, max_results)


def _ddg_search_fallback(query: str, max_results: int = 5) -> list[dict]:
    """Fallback using DuckDuckGo instant answer API (limited but no dependencies)."""
    url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
    req = Request(url, headers={"User-Agent": "Cronosaurus/1.0"})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []

        # Abstract (main answer)
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", "Answer"),
                "url": data.get("AbstractURL", ""),
                "snippet": data["Abstract"],
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                })
            if len(results) >= max_results:
                break

        if not results:
            results.append({
                "title": "No results",
                "url": "",
                "snippet": f"No results found for '{query}'. Try different keywords.",
            })

        return results[:max_results]
    except Exception as e:
        logger.error("DuckDuckGo fallback API error: %s", e)
        return [{"title": "Search error", "url": "", "snippet": str(e)}]


_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MAX_CONTENT_CHARS = 12000


def _download_page(url: str) -> str:
    """Download raw HTML from a URL."""
    req = Request(url, headers=_REQUEST_HEADERS)
    with urlopen(req, timeout=20) as resp:
        content_type = resp.headers.get("Content-Type", "")
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
        else:
            charset = "utf-8"
        return resp.read().decode(charset, errors="replace")


def _extract_text_bs4(html: str) -> tuple[str, str]:
    """Extract readable text using BeautifulSoup. Returns (title, body_text)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header",
                              "aside", "noscript", "iframe", "svg"]):
        tag.decompose()

    # Try to find the main content area
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

    # Collapse excessive blank lines
    import re
    text = re.sub(r"\n{3,}", "\n\n", text)

    return title, text


def _extract_text_fallback(html: str) -> tuple[str, str]:
    """Regex-based fallback when BeautifulSoup is unavailable."""
    import re
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for old, new in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        text = text.replace(old, new)
    return title, text


def _fetch_page(url: str) -> dict:
    """Fetch a web page and return structured content."""
    try:
        html = _download_page(url)
    except Exception as e:
        logger.error("Failed to download %s: %s", url, e)
        return {"success": False, "error": f"Failed to download page: {e}"}

    try:
        title, text = _extract_text_bs4(html)
    except Exception:
        title, text = _extract_text_fallback(html)

    truncated = False
    total_len = len(text)
    if total_len > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS]
        truncated = True

    return {
        "success": True,
        "url": url,
        "title": title,
        "content": text,
        "length": total_len,
        "truncated": truncated,
    }


def _scrape_page(url: str, extract: str) -> dict:
    """Scrape structured data from a web page."""
    try:
        html = _download_page(url)
    except Exception as e:
        logger.error("Failed to download %s: %s", url, e)
        return {"success": False, "error": f"Failed to download page: {e}"}

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {"success": False, "error": "BeautifulSoup not installed — scraping unavailable"}

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""

    extract_lower = extract.lower().strip()

    if extract_lower == "links":
        items = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if text and href and not href.startswith(("#", "javascript:")):
                items.append({"text": text[:120], "href": href})
        return {"success": True, "url": url, "title": title,
                "type": "links", "items": items[:100],
                "count": len(items)}

    if extract_lower == "headings":
        items = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            items.append({"level": int(tag.name[1]),
                          "text": tag.get_text(strip=True)[:200]})
        return {"success": True, "url": url, "title": title,
                "type": "headings", "items": items}

    if extract_lower == "images":
        items = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            alt = img.get("alt", "")
            if src:
                items.append({"src": src, "alt": alt[:200]})
        return {"success": True, "url": url, "title": title,
                "type": "images", "items": items[:50],
                "count": len(items)}

    if extract_lower == "tables":
        tables = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return {"success": True, "url": url, "title": title,
                "type": "tables", "tables": tables[:10],
                "count": len(tables)}

    if extract_lower == "meta":
        meta = {"title": title}
        for tag in soup.find_all("meta"):
            name = tag.get("name", tag.get("property", "")).lower()
            content = tag.get("content", "")
            if name and content:
                meta[name] = content[:500]
        return {"success": True, "url": url, "type": "meta", "meta": meta}

    # Treat as CSS selector
    try:
        elements = soup.select(extract)
        items = [{"tag": el.name,
                  "text": el.get_text(strip=True)[:500],
                  "attrs": {k: v for k, v in list(el.attrs.items())[:5]}}
                 for el in elements[:30]]
        return {"success": True, "url": url, "title": title,
                "type": "selector", "selector": extract,
                "items": items, "count": len(elements)}
    except Exception as e:
        return {"success": False, "error": f"Invalid CSS selector '{extract}': {e}"}


# ── Tool execution dispatcher ───────────────────────────────────

def execute_web_search_tool(tool_name: str, arguments: str | dict) -> dict:
    """Execute a web search tool call and return the result."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return {"success": False, "error": f"Invalid arguments: {arguments}"}

    if tool_name == "web_search":
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 5)
        if not query:
            return {"success": False, "error": "Missing required parameter: query"}

        logger.info("Web search: %s (max_results=%d)", query, max_results)
        results = _ddg_search(query, max_results)
        return {
            "success": True,
            "query": query,
            "results": results,
            "count": len(results),
        }

    elif tool_name == "web_fetch":
        url = arguments.get("url", "")
        if not url:
            return {"success": False, "error": "Missing required parameter: url"}

        logger.info("Web fetch: %s", url)
        return _fetch_page(url)

    elif tool_name == "web_scrape":
        url = arguments.get("url", "")
        extract = arguments.get("extract", "")
        if not url:
            return {"success": False, "error": "Missing required parameter: url"}
        if not extract:
            return {"success": False, "error": "Missing required parameter: extract"}

        logger.info("Web scrape: %s extract=%s", url, extract)
        return _scrape_page(url, extract)

    return {"success": False, "error": f"Unknown web search tool: {tool_name}"}
