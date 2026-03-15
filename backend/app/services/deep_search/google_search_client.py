"""
Google Custom Search API client.

Wraps the Google Programmable Search Engine JSON API.
Requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID.
"""

import json
import logging
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

_API_URL = "https://www.googleapis.com/customsearch/v1"


def search(
    query: str,
    api_key: str,
    engine_id: str,
    *,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Run a Google Custom Search query and return normalised results.

    Returns a list of dicts with keys: title, url, snippet, displayLink.
    Returns an empty list on error (logged, not raised).
    """
    if not query or not api_key or not engine_id:
        return []

    # Google API returns max 10 per page
    num = min(max_results, 10)

    params = urlencode({
        "key": api_key,
        "cx": engine_id,
        "q": query,
        "num": num,
    })
    url = f"{_API_URL}?{params}"

    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logger.error("Google Search API HTTP %s for query '%s': %s", e.code, query, body)
        return []
    except (URLError, TimeoutError) as e:
        logger.error("Google Search API network error for query '%s': %s", query, e)
        return []

    items = data.get("items", [])
    results: list[dict[str, Any]] = []
    for item in items:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "displayLink": item.get("displayLink", ""),
        })
    return results
