"""
File system tools — read, write, and list local files.

Allows agents to save reports, export CSV data, read config files,
and manage a workspace directory. Files are sandboxed to a configurable
workspace directory (default: backend/workspace/).
"""

import csv
import io
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Sandbox directory for file operations
WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent / "workspace"

# ── JSON-Schema definitions ─────────────────────────────────────

FILESYSTEM_TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file from the workspace. "
            "Returns the file content as text. For binary files, returns base64."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace (e.g. 'reports/daily.txt').",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file in the workspace. Creates the file and "
            "parent directories if they don't exist. Overwrites existing files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace (e.g. 'reports/daily.txt').",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "write_csv",
        "description": (
            "Write structured data as a CSV file. Pass headers and rows. "
            "Great for exporting tables, reports, and data analysis results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path for the CSV file (e.g. 'exports/costs.csv').",
                },
                "headers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column headers.",
                },
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "description": "Rows of data (each row is an array of values).",
                },
            },
            "required": ["path", "headers", "rows"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List files and directories in the workspace. "
            "Returns names, sizes, and types."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path (default: workspace root).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a file from the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path of the file to delete.",
                },
            },
            "required": ["path"],
        },
    },
]

FILESYSTEM_TOOL_NAMES = {d["name"] for d in FILESYSTEM_TOOL_DEFINITIONS}


def _safe_path(rel_path: str) -> Path:
    """Resolve a relative path within the workspace, preventing directory traversal."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    resolved = (WORKSPACE_DIR / rel_path).resolve()
    if not str(resolved).startswith(str(WORKSPACE_DIR.resolve())):
        raise ValueError("Path traversal detected — access denied")
    return resolved


def execute_filesystem_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    """Execute a filesystem tool call."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    try:
        if tool_name == "read_file":
            return _read_file(arguments)
        elif tool_name == "write_file":
            return _write_file(arguments)
        elif tool_name == "write_csv":
            return _write_csv(arguments)
        elif tool_name == "list_files":
            return _list_files(arguments)
        elif tool_name == "delete_file":
            return _delete_file(arguments)
        else:
            return {"success": False, "error": f"Unknown filesystem tool: {tool_name}"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error("Filesystem tool %s failed: %s", tool_name, e, exc_info=True)
        return {"success": False, "error": str(e)}


def _read_file(args: dict) -> dict:
    path = _safe_path(args.get("path", ""))
    if not path.exists():
        return {"success": False, "error": f"File not found: {args.get('path')}"}
    if not path.is_file():
        return {"success": False, "error": "Path is a directory, not a file"}
    size = path.stat().st_size
    if size > 5 * 1024 * 1024:
        return {"success": False, "error": f"File too large ({size} bytes, max 5MB)"}
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        import base64
        content = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"success": True, "path": args["path"], "encoding": "base64", "content": content, "size": size}
    return {"success": True, "path": args["path"], "content": content, "size": size}


def _write_file(args: dict) -> dict:
    path = _safe_path(args.get("path", ""))
    content = args.get("content", "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"success": True, "path": args["path"], "size": len(content.encode("utf-8"))}


def _write_csv(args: dict) -> dict:
    path = _safe_path(args.get("path", ""))
    headers = args.get("headers", [])
    rows = args.get("rows", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    return {"success": True, "path": args["path"], "rows_written": len(rows), "columns": len(headers)}


def _list_files(args: dict) -> dict:
    rel = args.get("path", "")
    path = _safe_path(rel) if rel else WORKSPACE_DIR
    if not path.exists():
        return {"success": False, "error": f"Directory not found: {rel}"}
    if not path.is_dir():
        return {"success": False, "error": "Path is a file, not a directory"}
    entries = []
    for item in sorted(path.iterdir()):
        entry = {"name": item.name, "type": "directory" if item.is_dir() else "file"}
        if item.is_file():
            entry["size"] = item.stat().st_size
        entries.append(entry)
    return {"success": True, "path": rel or ".", "entries": entries, "count": len(entries)}


def _delete_file(args: dict) -> dict:
    path = _safe_path(args.get("path", ""))
    if not path.exists():
        return {"success": False, "error": f"File not found: {args.get('path')}"}
    if not path.is_file():
        return {"success": False, "error": "Cannot delete directories"}
    path.unlink()
    return {"success": True, "path": args["path"], "deleted": True}
