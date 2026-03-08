"""
Twitch stream capture tool — fetch a live frame from any Twitch stream.

Captures the stream preview thumbnail (updated every few minutes by Twitch)
and returns it as a base64-encoded image that can be sent to a vision model
for analysis.

No API key required — uses Twitch's public CDN thumbnail endpoint.
"""

import base64
import json
import logging
import re
import time
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

# ── Metadata ────────────────────────────────────────────────────

TOOL_META = {
    "id": "twitch_capture",
    "label": "Twitch Stream Capture",
    "description": "Capture a live frame from any Twitch stream for visual analysis. Returns the stream thumbnail as an image.",
    "category": "custom",
    "requires_config": False,
}

# ── Tool definitions ────────────────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "capture_twitch_stream",
        "description": (
            "Capture a screenshot/frame from a live Twitch stream. "
            "Returns the current stream preview image as base64-encoded data "
            "that can be analyzed by a vision model. Also returns stream metadata. "
            "The image is a thumbnail that Twitch updates every few minutes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": (
                        "The Twitch channel name or full URL. "
                        "Examples: 'shroud', 'al159', 'https://twitch.tv/shroud', "
                        "'https://m.twitch.tv/al159'"
                    ),
                },
                "width": {
                    "type": "integer",
                    "description": "Image width in pixels. Default 1920. Max 1920.",
                },
                "height": {
                    "type": "integer",
                    "description": "Image height in pixels. Default 1080. Max 1080.",
                },
            },
            "required": ["channel"],
        },
    },
    {
        "name": "check_twitch_status",
        "description": (
            "Check if a Twitch channel is currently live without downloading the image. "
            "Faster than capture_twitch_stream — use this when you only need to know "
            "if someone is streaming."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "The Twitch channel name or full URL.",
                },
            },
            "required": ["channel"],
        },
    },
]

TOOL_NAMES: set[str] = {t["name"] for t in TOOL_DEFINITIONS}

# ── Instructions ────────────────────────────────────────────────

INSTRUCTIONS_SUFFIX = """
You have access to Twitch stream tools.

Tools:
- capture_twitch_stream: Captures a live frame (thumbnail) from a Twitch stream and returns it as a base64 image. Use this when the user wants to SEE or ANALYZE what's happening on a stream.
- check_twitch_status: Quickly checks if a channel is live. Use this when the user just wants to know if someone is streaming.

The captured image is a preview thumbnail that Twitch updates every few minutes. It won't show real-time frame-by-frame video, but gives a good snapshot of the current stream state.

When the user provides a Twitch URL like https://twitch.tv/username or https://m.twitch.tv/username, extract the channel name automatically.
"""

# ── Helpers ─────────────────────────────────────────────────────

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _extract_username(channel: str) -> str:
    """Extract Twitch username from a channel name or URL."""
    channel = channel.strip()

    # Handle URLs: https://twitch.tv/username, https://m.twitch.tv/username, etc.
    url_match = re.search(r'twitch\.tv/([a-zA-Z0-9_]+)', channel)
    if url_match:
        return url_match.group(1).lower()

    # Handle plain username (strip any leading @ or #)
    username = channel.lstrip("@#").strip().lower()

    # Validate: Twitch usernames are 1-25 alphanumeric + underscore
    if re.match(r'^[a-z0-9_]{1,25}$', username):
        return username

    return username


def _get_thumbnail_url(username: str, width: int = 1920, height: int = 1080) -> str:
    """Build the Twitch preview thumbnail URL."""
    # Clamp dimensions
    width = min(max(width, 320), 1920)
    height = min(max(height, 180), 1080)
    # Add cache-buster to get a fresh image
    cache_buster = int(time.time())
    return f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{username}-{width}x{height}.jpg?t={cache_buster}"


def _fetch_image(url: str) -> tuple[bytes | None, str]:
    """Fetch image bytes from a URL. Returns (data, error)."""
    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if resp.status != 200:
                return None, f"HTTP {resp.status}"
            data = resp.read()
            if len(data) < 1000:
                # Twitch returns a tiny placeholder when the stream is offline
                return None, "offline"
            return data, ""
    except HTTPError as e:
        if e.code == 404:
            return None, "offline"
        return None, f"HTTP error {e.code}"
    except URLError as e:
        return None, f"Connection error: {e.reason}"
    except Exception as e:
        return None, str(e)


def _check_stream_online(username: str) -> bool:
    """Quick check if a stream is live by testing the thumbnail URL."""
    url = _get_thumbnail_url(username, 320, 180)
    data, err = _fetch_image(url)
    return data is not None and err == ""


# ── Handler ─────────────────────────────────────────────────────

def execute_tool(tool_name: str, arguments: str | dict, **kwargs) -> dict[str, Any]:
    """Dispatch a Twitch tool call."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}

    if tool_name == "capture_twitch_stream":
        channel = arguments.get("channel", "")
        if not channel:
            return {"success": False, "error": "Channel name or URL is required."}

        username = _extract_username(channel)
        width = min(arguments.get("width", 1920), 1920)
        height = min(arguments.get("height", 1080), 1080)

        logger.info("Capturing Twitch stream: %s (%dx%d)", username, width, height)

        url = _get_thumbnail_url(username, width, height)
        data, err = _fetch_image(url)

        if err == "offline":
            return {
                "success": False,
                "channel": username,
                "is_live": False,
                "error": f"Channel '{username}' is not currently live. The thumbnail is only available when the stream is active.",
                "thumbnail_url": url,
            }
        if err:
            return {"success": False, "channel": username, "error": f"Failed to capture stream: {err}"}

        # Encode as base64
        image_b64 = base64.b64encode(data).decode("ascii")

        return {
            "success": True,
            "channel": username,
            "is_live": True,
            "image_base64": image_b64,
            "image_media_type": "image/jpeg",
            "image_size_bytes": len(data),
            "width": width,
            "height": height,
            "thumbnail_url": url.split("?")[0],  # without cache buster
            "note": "Image captured successfully. This is a stream preview thumbnail that Twitch updates every few minutes.",
        }

    elif tool_name == "check_twitch_status":
        channel = arguments.get("channel", "")
        if not channel:
            return {"success": False, "error": "Channel name or URL is required."}

        username = _extract_username(channel)
        logger.info("Checking Twitch status: %s", username)

        is_live = _check_stream_online(username)

        return {
            "success": True,
            "channel": username,
            "is_live": is_live,
            "status": "live" if is_live else "offline",
            "message": f"Channel '{username}' is currently {'LIVE' if is_live else 'OFFLINE'}.",
        }

    return {"success": False, "error": f"Unknown tool: {tool_name}"}
