"""
Website screenshot tools — capture screenshots of any URL.

Uses Playwright (headless Chromium) to render pages and capture screenshots.
Returns base64-encoded images that can be sent to a vision model for analysis
or included in notifications.

Requires: pip install playwright && python -m playwright install chromium
"""

import base64
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SCREENSHOT_TOOL_DEFINITIONS = [
    {
        "name": "capture_screenshot",
        "description": (
            "Take a screenshot of any website URL. Returns a base64-encoded image "
            "of the rendered page. The image can be analyzed by the vision model "
            "or included in notifications. Great for monitoring website changes, "
            "capturing dashboards, or documenting web pages."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to screenshot (e.g. 'https://example.com').",
                },
                "width": {
                    "type": "integer",
                    "description": "Viewport width in pixels. Defaults to 1280.",
                },
                "height": {
                    "type": "integer",
                    "description": "Viewport height in pixels. Defaults to 720.",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Capture the full scrollable page, not just the viewport. Defaults to false.",
                },
                "wait_seconds": {
                    "type": "integer",
                    "description": "Seconds to wait after page load before capturing. Defaults to 2.",
                },
            },
            "required": ["url"],
        },
    },
]

SCREENSHOT_TOOL_NAMES = {d["name"] for d in SCREENSHOT_TOOL_DEFINITIONS}


def execute_screenshot_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    if tool_name != "capture_screenshot":
        return {"success": False, "error": f"Unknown screenshot tool: {tool_name}"}

    url = arguments.get("url", "")
    if not url:
        return {"success": False, "error": "url is required"}

    # Validate URL
    if not url.startswith(("http://", "https://")):
        return {"success": False, "error": "URL must start with http:// or https://"}

    width = min(arguments.get("width", 1280), 1920)
    height = min(arguments.get("height", 720), 1080)
    full_page = arguments.get("full_page", False)
    wait_seconds = min(arguments.get("wait_seconds", 2), 10)

    try:
        img_b64 = _capture_with_playwright(url, width, height, full_page, wait_seconds)
    except RuntimeError as e:
        # Playwright not available — try fallback
        logger.warning("Playwright not available: %s — trying fallback", e)
        try:
            img_b64 = _capture_fallback(url, width, height)
        except Exception as fallback_err:
            return {
                "success": False,
                "error": (
                    f"Screenshot capture failed. Primary (Playwright): {e}. "
                    f"Fallback: {fallback_err}. "
                    "Install Playwright: pip install playwright && python -m playwright install chromium"
                ),
            }

    return {
        "success": True,
        "url": url,
        "image_base64": img_b64,
        "image_media_type": "image/png",
        "width": width,
        "height": height,
        "full_page": full_page,
    }


def _capture_with_playwright(
    url: str, width: int, height: int, full_page: bool, wait_seconds: int
) -> str:
    """Capture screenshot using Playwright headless browser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright package not installed")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url, wait_until="networkidle", timeout=30000)
            if wait_seconds > 0:
                page.wait_for_timeout(wait_seconds * 1000)
            screenshot_bytes = page.screenshot(full_page=full_page, type="png")
            return base64.b64encode(screenshot_bytes).decode("ascii")
        finally:
            browser.close()


def _capture_fallback(url: str, width: int, height: int) -> str:
    """Fallback: use a public screenshot API if Playwright is not available."""
    from urllib.request import Request, urlopen

    # Use the free screenshotlayer-style API via Google's PageSpeed
    # This is a lightweight fallback — not as reliable as Playwright
    api_url = (
        f"https://image.thum.io/get/width/{width}/crop/{height}/"
        f"noanimate/{url}"
    )
    req = Request(api_url, headers={"User-Agent": "Cronosaurus/1.0"})
    with urlopen(req, timeout=20) as resp:
        img_data = resp.read()
    if len(img_data) < 1000:
        raise RuntimeError("Fallback API returned invalid response")
    return base64.b64encode(img_data).decode("ascii")
