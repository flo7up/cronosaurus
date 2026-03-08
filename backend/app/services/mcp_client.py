"""
MCP (Model Context Protocol) client for connecting to external MCP servers.

Supports the MCP Streamable HTTP transport:
  - POST to the server URL with JSON-RPC 2.0 messages
  - Discovers tools via tools/list
  - Executes tools via tools/call

Each MCP server configured by the user becomes a tool category in the
agent's tool catalog, with its tools exposed as function-calling definitions.
"""

import json
import logging
import threading
import time
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

# Cache discovered tools per server (server_id → {tools, fetched_at})
_tool_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 300  # refresh tool list every 5 minutes


def _jsonrpc_request(url: str, method: str, params: dict | None = None, api_key: str = "") -> Any:
    """Send a JSON-RPC 2.0 request to an MCP server and return the result."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }
    if params:
        payload["params"] = params

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "Cronosaurus/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        # Azure Functions uses x-functions-key header for auth
        headers["x-functions-key"] = api_key

    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="POST")

    try:
        with urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            # MCP Streamable HTTP may return multiple lines (SSE-style)
            # or a single JSON-RPC response. Parse the last valid JSON object.
            result = _parse_jsonrpc_response(body)
            return result
    except URLError as e:
        logger.error("MCP request to %s failed: %s", url, e)
        raise ConnectionError(f"Failed to connect to MCP server: {e}")
    except Exception as e:
        logger.error("MCP request error: %s", e)
        raise


def _parse_jsonrpc_response(body: str) -> Any:
    """Parse a JSON-RPC 2.0 response body. Handles both plain JSON and SSE streams."""
    # Try plain JSON first
    try:
        parsed = json.loads(body)
        if "error" in parsed and parsed["error"]:
            err = parsed["error"]
            raise RuntimeError(f"MCP error {err.get('code', '?')}: {err.get('message', 'Unknown error')}")
        return parsed.get("result")
    except json.JSONDecodeError:
        pass

    # Try SSE format: look for lines starting with "data: "
    last_result = None
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            json_str = line[6:]
            try:
                parsed = json.loads(json_str)
                if "result" in parsed:
                    last_result = parsed["result"]
                elif "error" in parsed and parsed["error"]:
                    err = parsed["error"]
                    raise RuntimeError(f"MCP error {err.get('code', '?')}: {err.get('message', 'Unknown error')}")
            except json.JSONDecodeError:
                continue

    if last_result is not None:
        return last_result

    raise RuntimeError(f"Could not parse MCP response: {body[:200]}")


def discover_tools(server_id: str, url: str, api_key: str = "") -> list[dict]:
    """Discover tools from an MCP server via tools/list.

    Returns a list of MCP tool definitions:
    [{"name": "...", "description": "...", "inputSchema": {...}}, ...]

    Results are cached for CACHE_TTL_SECONDS.

    For Azure Functions MCP servers, automatically tries the standard
    ``/runtime/webhooks/mcp`` path if the given URL fails.
    """
    with _cache_lock:
        cached = _tool_cache.get(server_id)
        if cached and (time.time() - cached["fetched_at"]) < CACHE_TTL_SECONDS:
            return cached["tools"]

    # Build a list of URLs to try (primary first, then Azure Functions fallback)
    urls_to_try = [url]
    if ".azurewebsites.net" in url and "/runtime/webhooks/mcp" not in url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        fallback = f"{parsed.scheme}://{parsed.netloc}/runtime/webhooks/mcp"
        urls_to_try.append(fallback)

    last_error = None
    for attempt_url in urls_to_try:
        try:
            result = _jsonrpc_request(attempt_url, "tools/list", api_key=api_key)
            tools = result.get("tools", []) if isinstance(result, dict) else result if isinstance(result, list) else []

            with _cache_lock:
                _tool_cache[server_id] = {"tools": tools, "fetched_at": time.time()}

            if attempt_url != url:
                logger.info("MCP server %s: primary URL failed, succeeded with %s", server_id, attempt_url)
            logger.info("Discovered %d tools from MCP server %s (%s)", len(tools), server_id, attempt_url)
            return tools
        except Exception as e:
            last_error = e
            logger.warning("MCP discover attempt failed for %s at %s: %s", server_id, attempt_url, e)

    logger.error("Failed to discover tools from MCP server %s (tried %d URLs): %s", server_id, len(urls_to_try), last_error)
    # Return stale cache if available
    with _cache_lock:
        cached = _tool_cache.get(server_id)
        if cached:
            return cached["tools"]
    return []


def call_tool(url: str, tool_name: str, arguments: dict, api_key: str = "") -> dict:
    """Execute a tool call on an MCP server via tools/call.

    Returns the tool result as a dict.
    For Azure Functions MCP servers, automatically tries the standard
    ``/runtime/webhooks/mcp`` path if the given URL fails.
    """
    # Build URLs to try (primary + Azure Functions fallback)
    urls_to_try = [url]
    if ".azurewebsites.net" in url and "/runtime/webhooks/mcp" not in url:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        fallback = f"{parsed.scheme}://{parsed.netloc}/runtime/webhooks/mcp"
        urls_to_try.append(fallback)

    last_error = None
    for attempt_url in urls_to_try:
        try:
            result = _jsonrpc_request(
                attempt_url,
                "tools/call",
                params={"name": tool_name, "arguments": arguments},
                api_key=api_key,
            )

            # MCP tools/call returns {"content": [...]} with text/image blocks
            if isinstance(result, dict):
                content = result.get("content", [])
                if isinstance(content, list):
                    # Extract text content blocks
                    texts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                texts.append(block.get("text", ""))
                            elif block.get("type") == "image":
                                texts.append(f"[Image: {block.get('mimeType', 'image')}]")
                            else:
                                texts.append(str(block))
                        else:
                            texts.append(str(block))

                    return {
                        "success": not result.get("isError", False),
                        "result": "\n".join(texts) if texts else json.dumps(result),
                    }
                return {"success": True, "result": json.dumps(result)}

            return {"success": True, "result": str(result)}

        except Exception as e:
            last_error = e
            logger.warning("MCP tool call %s at %s failed: %s", tool_name, attempt_url, e)

    logger.error("MCP tool call %s failed on all URLs: %s", tool_name, last_error)
    return {"success": False, "error": f"MCP tool call failed: {last_error}"}


def mcp_tools_to_function_defs(server_name: str, mcp_tools: list[dict]) -> list[dict]:
    """Convert MCP tool definitions to OpenAI function-calling format.

    MCP format:  {"name": "...", "description": "...", "inputSchema": {...}}
    OpenAI format: {"name": "...", "description": "...", "parameters": {...}}

    Tool names are prefixed with the server ID to avoid collisions:
    e.g. "mcp_myserver_search" for a tool named "search" from server "myserver".
    """
    result = []
    for tool in mcp_tools:
        name = tool.get("name", "")
        if not name:
            continue

        # Use inputSchema directly as parameters (it's already JSON Schema)
        input_schema = tool.get("inputSchema", {"type": "object", "properties": {}})

        result.append({
            "name": f"mcp_{_sanitize(server_name)}_{name}",
            "description": tool.get("description", f"Tool from {server_name}"),
            "parameters": input_schema,
            "_mcp_original_name": name,  # preserve for dispatch
        })

    return result


def _sanitize(name: str) -> str:
    """Sanitize a server name for use in a tool name prefix."""
    import re
    return re.sub(r"[^a-zA-Z0-9]", "_", name).lower().strip("_")[:20]


def invalidate_cache(server_id: str | None = None):
    """Clear the tool cache for a specific server or all servers."""
    with _cache_lock:
        if server_id:
            _tool_cache.pop(server_id, None)
        else:
            _tool_cache.clear()
