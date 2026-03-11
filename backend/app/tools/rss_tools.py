"""
RSS feed tools — read and monitor RSS/Atom feeds.

Supports any standard RSS 2.0 or Atom feed. No external dependencies
beyond Python's built-in xml.etree and urllib.
"""

import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Cronosaurus/1.0 RSS Reader"}

RSS_TOOL_DEFINITIONS = [
    {
        "name": "read_rss_feed",
        "description": (
            "Fetch and parse an RSS or Atom feed URL. Returns the latest articles "
            "with titles, links, summaries, and publication dates. "
            "Great for monitoring news, blogs, release notes, and any content with an RSS feed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The RSS or Atom feed URL.",
                },
                "max_items": {
                    "type": "integer",
                    "description": "Maximum number of items to return. Defaults to 10.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "check_rss_new_items",
        "description": (
            "Check an RSS feed for new items since a specific date. "
            "Returns only articles published after the given date. Useful for "
            "monitoring feeds on a schedule — call with the last check time "
            "to get only new content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The RSS or Atom feed URL.",
                },
                "since": {
                    "type": "string",
                    "description": (
                        "ISO 8601 date/time to filter from (e.g. '2026-03-10T00:00:00'). "
                        "Only returns items published after this time."
                    ),
                },
                "max_items": {
                    "type": "integer",
                    "description": "Maximum number of items to return. Defaults to 20.",
                },
            },
            "required": ["url", "since"],
        },
    },
]

RSS_TOOL_NAMES = {d["name"] for d in RSS_TOOL_DEFINITIONS}


def execute_rss_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    try:
        if tool_name == "read_rss_feed":
            return _read_feed(arguments)
        elif tool_name == "check_rss_new_items":
            return _check_new_items(arguments)
        else:
            return {"success": False, "error": f"Unknown RSS tool: {tool_name}"}
    except Exception as e:
        logger.error("RSS tool %s failed: %s", tool_name, e, exc_info=True)
        return {"success": False, "error": str(e)}


def _fetch_feed(url: str) -> list[dict]:
    """Fetch and parse an RSS/Atom feed, returning normalized items."""
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=15) as resp:
        data = resp.read()

    root = ET.fromstring(data)

    items = []

    # RSS 2.0
    for item in root.findall(".//item"):
        entry = _parse_rss_item(item)
        if entry:
            items.append(entry)

    # Atom (if no RSS items found)
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            parsed = _parse_atom_entry(entry, ns)
            if parsed:
                items.append(parsed)
        # Try without namespace (some feeds)
        if not items:
            for entry in root.findall(".//entry"):
                parsed = _parse_atom_entry_no_ns(entry)
                if parsed:
                    items.append(parsed)

    return items


def _parse_rss_item(item: ET.Element) -> dict | None:
    title = _text(item, "title")
    link = _text(item, "link")
    desc = _text(item, "description")
    pub_date = _text(item, "pubDate")

    if not title and not link:
        return None

    entry: dict = {"title": title or "(no title)"}
    if link:
        entry["link"] = link
    if desc:
        # Strip HTML tags for a clean summary
        entry["summary"] = _strip_html(desc)[:500]
    if pub_date:
        entry["published"] = _parse_date(pub_date)

    author = _text(item, "author") or _text(item, "{http://purl.org/dc/elements/1.1/}creator")
    if author:
        entry["author"] = author

    return entry


def _parse_atom_entry(entry: ET.Element, ns: dict) -> dict | None:
    title = _text(entry, "atom:title", ns)
    link_el = entry.find("atom:link", ns)
    link = link_el.get("href", "") if link_el is not None else ""
    summary = _text(entry, "atom:summary", ns) or _text(entry, "atom:content", ns)
    updated = _text(entry, "atom:updated", ns) or _text(entry, "atom:published", ns)

    if not title and not link:
        return None

    result: dict = {"title": title or "(no title)"}
    if link:
        result["link"] = link
    if summary:
        result["summary"] = _strip_html(summary)[:500]
    if updated:
        result["published"] = _parse_date(updated)

    author_el = entry.find("atom:author/atom:name", ns)
    if author_el is not None and author_el.text:
        result["author"] = author_el.text

    return result


def _parse_atom_entry_no_ns(entry: ET.Element) -> dict | None:
    title = _text(entry, "title")
    link_el = entry.find("link")
    link = link_el.get("href", "") if link_el is not None else ""
    summary = _text(entry, "summary") or _text(entry, "content")
    updated = _text(entry, "updated") or _text(entry, "published")

    if not title and not link:
        return None

    result: dict = {"title": title or "(no title)"}
    if link:
        result["link"] = link
    if summary:
        result["summary"] = _strip_html(summary)[:500]
    if updated:
        result["published"] = _parse_date(updated)
    return result


def _text(el: ET.Element, tag: str, ns: dict | None = None) -> str:
    child = el.find(tag, ns) if ns else el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _strip_html(html: str) -> str:
    """Simple HTML tag stripping."""
    import re
    clean = re.sub(r"<[^>]+>", "", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _parse_date(date_str: str) -> str:
    """Parse various date formats to ISO 8601."""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.isoformat()
    except Exception:
        pass
    return date_str


def _read_feed(args: dict) -> dict:
    url = args.get("url", "")
    max_items = args.get("max_items", 10)
    if not url:
        return {"success": False, "error": "url is required"}

    items = _fetch_feed(url)
    return {
        "success": True,
        "url": url,
        "items": items[:max_items],
        "total_items": len(items),
        "returned": min(len(items), max_items),
    }


def _check_new_items(args: dict) -> dict:
    url = args.get("url", "")
    since_str = args.get("since", "")
    max_items = args.get("max_items", 20)

    if not url or not since_str:
        return {"success": False, "error": "url and since are required"}

    try:
        since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
    except Exception:
        return {"success": False, "error": f"Invalid since date: {since_str}"}

    items = _fetch_feed(url)

    # Filter to items published after `since`
    new_items = []
    for item in items:
        pub = item.get("published", "")
        if pub:
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt > since:
                    new_items.append(item)
            except Exception:
                new_items.append(item)  # Include if we can't parse the date
        else:
            new_items.append(item)  # Include if no date

    return {
        "success": True,
        "url": url,
        "since": since_str,
        "new_items": new_items[:max_items],
        "new_count": len(new_items),
        "total_feed_items": len(items),
    }
