"""
Page fetcher — download web pages with safe timeouts and error handling.

Returns raw HTML text.  Failures are logged and returned as empty strings
so the caller can skip broken pages without aborting the research loop.
"""

import logging
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_TIMEOUT = 15  # seconds
_MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024  # 2 MB safety cap


def fetch(url: str, *, timeout: int = _TIMEOUT) -> str:
    """Download the HTML of *url*.  Returns empty string on any error."""
    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            # Skip binary content
            if not any(ct in content_type for ct in ("text/", "html", "xml", "json")):
                logger.debug("Skipping non-text content at %s (%s)", url, content_type)
                return ""
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            raw = resp.read(_MAX_DOWNLOAD_BYTES)
            return raw.decode(charset, errors="replace")
    except HTTPError as e:
        logger.warning("Page fetch HTTP %s: %s", e.code, url)
    except (URLError, TimeoutError) as e:
        logger.warning("Page fetch error for %s: %s", url, e)
    except Exception as e:
        logger.warning("Page fetch unexpected error for %s: %s", url, e)
    return ""
