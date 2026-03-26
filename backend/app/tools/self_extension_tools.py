"""
Self-extension tools — let an agent create, test, and manage its own tools
at runtime.

Agent-created tools are persisted to the generated_tool_store and
registered in the TOOL_CATALOG dynamically. They are clearly marked
as "agent_created" so humans can review, deactivate, or delete them.
"""

import json
import logging
import re
import textwrap
from typing import Any

logger = logging.getLogger(__name__)

# ── Allowlisted imports for generated tool code ─────────────────
# Only these modules may be imported inside agent-generated tools.
# This prevents access to OS, subprocess, file system, etc.
ALLOWED_IMPORTS = frozenset({
    "json", "re", "math", "statistics", "datetime", "time",
    "hashlib", "hmac", "base64", "urllib.parse", "html",
    "collections", "itertools", "functools", "operator",
    "string", "textwrap", "unicodedata", "decimal", "fractions",
    "random", "uuid", "copy", "io", "csv",
    "requests", "httpx",
    "bs4", "lxml",
    "xml.etree.ElementTree",
})

# ── Tool definitions (exposed to the LLM) ──────────────────────

SELF_EXTENSION_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "create_agent_tool",
        "description": (
            "Create a brand-new tool that you (the agent) can use in future conversations. "
            "Use this when you detect a missing capability that no existing tool provides. "
            "You must provide the tool specification (name, description, parameter schema) "
            "AND the Python implementation code. The tool will be registered immediately "
            "and can be activated on any agent. "
            "IMPORTANT: The code must define a function called `execute_tool(tool_name, arguments, **kwargs)` "
            "that returns a dict. Only standard library modules and requests/bs4/httpx are allowed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_id": {
                    "type": "string",
                    "description": "Unique identifier for the tool category (lowercase_with_underscores, e.g. 'web_scraper').",
                },
                "label": {
                    "type": "string",
                    "description": "Human-readable label for the tool (e.g. 'Web Scraper').",
                },
                "description": {
                    "type": "string",
                    "description": "One-line description of what the tool does.",
                },
                "functions": {
                    "type": "array",
                    "description": "List of function definitions (OpenAI function-calling schema).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Function name (globally unique)."},
                            "description": {"type": "string", "description": "What this function does."},
                            "parameters": {
                                "type": "object",
                                "description": "JSON Schema for the function parameters.",
                            },
                        },
                        "required": ["name", "description", "parameters"],
                    },
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Python source code for the tool. Must define: "
                        "`def execute_tool(tool_name: str, arguments: dict, **kwargs) -> dict`. "
                        "Only allowed imports: " + ", ".join(sorted(ALLOWED_IMPORTS)) + ". "
                        "The function must return a dict with at least a 'success' key."
                    ),
                },
            },
            "required": ["tool_id", "label", "description", "functions", "code"],
        },
    },
    {
        "name": "test_agent_tool",
        "description": (
            "Test an agent-created tool by executing it with sample arguments. "
            "Use this to verify the tool works before relying on it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tool_id": {
                    "type": "string",
                    "description": "The tool_id of the agent-created tool to test.",
                },
                "function_name": {
                    "type": "string",
                    "description": "Which function to test.",
                },
                "test_arguments": {
                    "type": "object",
                    "description": "Arguments to pass to the function.",
                },
            },
            "required": ["tool_id", "function_name", "test_arguments"],
        },
    },
    {
        "name": "list_agent_created_tools",
        "description": (
            "List all tools that were created by agents (not human-added). "
            "Shows their status (active/inactive), creator, and description."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]

SELF_EXTENSION_TOOL_NAMES: set[str] = {t["name"] for t in SELF_EXTENSION_TOOL_DEFINITIONS}

SELF_EXTENSION_INSTRUCTIONS_SUFFIX = """

You have access to self-extension tools that let you create your own tools at runtime.

Tools: create_agent_tool, test_agent_tool, list_agent_created_tools

WHEN TO USE:
- When you detect a capability gap — you need to do something that no existing tool supports.
- When the user asks you to build a tool for a specific purpose.

RULES:
- Always provide working, tested Python code.
- Only use allowed imports (standard library + requests, httpx, bs4).
- The code MUST define `def execute_tool(tool_name, arguments, **kwargs) -> dict`.
- After creating a tool, test it with test_agent_tool before declaring success.
- Tool IDs must be lowercase_with_underscores and globally unique.
- Keep tools focused — one tool per capability area.
"""


def execute_self_extension_tool(
    tool_name: str,
    arguments: str | dict,
    agent_id: str,
) -> dict[str, Any]:
    """Dispatch a self-extension tool call."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = {}

    if tool_name == "create_agent_tool":
        return _create_agent_tool(arguments, agent_id)
    elif tool_name == "test_agent_tool":
        return _test_agent_tool(arguments)
    elif tool_name == "list_agent_created_tools":
        return _list_agent_created_tools()
    return {"success": False, "error": f"Unknown self_extension function: {tool_name}"}


# ── Validators ──────────────────────────────────────────────────

_TOOL_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


def _validate_tool_id(tool_id: str) -> str | None:
    """Return error message if tool_id is invalid, else None."""
    if not _TOOL_ID_RE.match(tool_id):
        return (
            f"Invalid tool_id '{tool_id}'. Must be 2-49 chars, lowercase, "
            "start with a letter, only a-z 0-9 and underscores."
        )
    # Check for collisions with existing catalog
    from app.services.agent_service import TOOL_CATALOG_META
    if tool_id in TOOL_CATALOG_META:
        # Allow if it's an existing generated tool (update scenario)
        from app.services.generated_tool_store import generated_tool_store
        existing = generated_tool_store.get_tool_by_tool_id(tool_id)
        if not existing:
            return f"tool_id '{tool_id}' conflicts with an existing built-in tool."
    return None


def _validate_code(code: str) -> str | None:
    """Validate generated tool code for safety. Returns error or None."""
    if not code or not code.strip():
        return "Code cannot be empty."

    # Check that execute_tool is defined
    if "def execute_tool(" not in code:
        return "Code must define `def execute_tool(tool_name, arguments, **kwargs) -> dict`."

    # Scan for disallowed imports
    # Match: import X, from X import Y
    import_pattern = re.compile(
        r"^\s*(?:import|from)\s+([\w.]+)", re.MULTILINE
    )
    for match in import_pattern.finditer(code):
        module = match.group(1).split(".")[0]
        # Allow sub-modules of allowed packages
        full_module = match.group(1)
        if full_module not in ALLOWED_IMPORTS and module not in {
            m.split(".")[0] for m in ALLOWED_IMPORTS
        }:
            return (
                f"Import '{full_module}' is not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_IMPORTS))}"
            )

    # Block dangerous patterns
    dangerous = [
        (r"\bos\.", "Direct os module access"),
        (r"\bsubprocess\b", "subprocess module"),
        (r"\b__import__\b", "__import__ builtin"),
        (r"\beval\s*\(", "eval()"),
        (r"\bexec\s*\(", "exec()"),
        (r"\bcompile\s*\(", "compile()"),
        (r"\bgetattr\s*\(\s*__builtins__", "builtins access"),
        (r"\bopen\s*\(", "open() — use requests for network I/O"),
        (r"\bglobals\s*\(", "globals()"),
        (r"\bsys\.", "sys module access"),
        (r"\bshutil\b", "shutil module"),
        (r"\bpickle\b", "pickle module"),
        (r"\bsocket\b", "raw socket access"),
        (r"\bctypes\b", "ctypes module"),
    ]
    for pattern, label in dangerous:
        if re.search(pattern, code):
            return f"Disallowed pattern detected: {label}"

    # Try to compile the code to catch syntax errors
    try:
        compile(code, "<generated_tool>", "exec")
    except SyntaxError as e:
        return f"Syntax error in code: {e}"

    return None


def _validate_functions(functions: list[dict]) -> str | None:
    """Validate function definitions. Returns error or None."""
    if not functions:
        return "At least one function definition is required."
    names = set()
    for fn in functions:
        name = fn.get("name", "")
        if not name or not re.match(r"^[a-z][a-z0-9_]{1,48}$", name):
            return f"Invalid function name: '{name}'"
        if name in names:
            return f"Duplicate function name: '{name}'"
        names.add(name)

        # Check for collision with existing function names
        from app.services.agent_service import TOOL_NAME_MAP
        if name in TOOL_NAME_MAP:
            from app.services.generated_tool_store import generated_tool_store
            existing = generated_tool_store.get_tool_by_tool_id(TOOL_NAME_MAP[name])
            if not existing:
                return f"Function name '{name}' conflicts with an existing built-in function."
    return None


# ── Handlers ────────────────────────────────────────────────────

def _create_agent_tool(args: dict, agent_id: str) -> dict[str, Any]:
    """Create and register a new agent-generated tool."""
    tool_id = args.get("tool_id", "").strip()
    label = args.get("label", "").strip()
    description = args.get("description", "").strip()
    functions = args.get("functions", [])
    code = args.get("code", "")

    # Validate
    err = _validate_tool_id(tool_id)
    if err:
        return {"success": False, "error": err}
    err = _validate_functions(functions)
    if err:
        return {"success": False, "error": err}
    err = _validate_code(code)
    if err:
        return {"success": False, "error": err}

    if not label:
        return {"success": False, "error": "Label is required."}
    if not description:
        return {"success": False, "error": "Description is required."}

    # Persist
    from app.services.generated_tool_store import generated_tool_store
    if not generated_tool_store.is_ready:
        return {"success": False, "error": "Generated tool store is not initialized."}

    # Check if tool_id already exists (update case)
    existing = generated_tool_store.get_tool_by_tool_id(tool_id)
    if existing:
        generated_tool_store.update_tool(existing["id"], {
            "label": label,
            "description": description,
            "functions": functions,
            "code": code,
            "created_by_agent_id": agent_id,
            "active": True,
        })
        doc = generated_tool_store.get_tool(existing["id"])
    else:
        doc = generated_tool_store.create_tool(
            tool_id=tool_id,
            label=label,
            description=description,
            functions=functions,
            code=code,
            created_by_agent_id=agent_id,
        )

    # Register in the runtime catalog
    _register_generated_tool(doc)

    return {
        "success": True,
        "tool_id": tool_id,
        "doc_id": doc["id"],
        "message": f"Tool '{label}' created and registered. Use test_agent_tool to verify it works.",
    }


def _test_agent_tool(args: dict) -> dict[str, Any]:
    """Test an agent-created tool with sample arguments."""
    tool_id = args.get("tool_id", "")
    function_name = args.get("function_name", "")
    test_arguments = args.get("test_arguments", {})

    from app.services.generated_tool_store import generated_tool_store
    doc = generated_tool_store.get_tool_by_tool_id(tool_id)
    if not doc:
        return {"success": False, "error": f"No agent-created tool with tool_id '{tool_id}' found."}

    # Execute in sandbox
    try:
        result = _execute_generated_code(doc["code"], function_name, test_arguments)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": f"Tool execution failed: {e}"}


def _list_agent_created_tools() -> dict[str, Any]:
    """List all agent-created tools."""
    from app.services.generated_tool_store import generated_tool_store
    if not generated_tool_store.is_ready:
        return {"success": True, "tools": []}

    tools = generated_tool_store.list_tools()
    return {
        "success": True,
        "tools": [
            {
                "doc_id": t["id"],
                "tool_id": t["tool_id"],
                "label": t["label"],
                "description": t["description"],
                "active": t["active"],
                "created_by_agent_id": t["created_by_agent_id"],
                "functions": [f["name"] for f in t.get("functions", [])],
                "created_at": t["created_at"],
            }
            for t in tools
        ],
    }


# ── Runtime registration ───────────────────────────────────────

def _register_generated_tool(doc: dict) -> None:
    """Register a generated tool in the live TOOL_CATALOG and maps."""
    from app.services.agent_service import TOOL_CATALOG, TOOL_CATALOG_META, TOOL_NAME_MAP

    tool_id = doc["tool_id"]
    functions = doc.get("functions", [])

    TOOL_CATALOG[tool_id] = functions
    TOOL_CATALOG_META[tool_id] = {
        "label": f"🤖 {doc['label']}",
        "description": doc["description"],
        "category": "agent_created",
        "requires_config": False,
        "agent_created": True,
    }
    for fn in functions:
        TOOL_NAME_MAP[fn["name"]] = tool_id

    logger.info("Registered generated tool '%s' with %d functions", tool_id, len(functions))


def unregister_generated_tool(tool_id: str) -> None:
    """Remove a generated tool from the live TOOL_CATALOG and maps."""
    from app.services.agent_service import TOOL_CATALOG, TOOL_CATALOG_META, TOOL_NAME_MAP

    defs = TOOL_CATALOG.pop(tool_id, [])
    TOOL_CATALOG_META.pop(tool_id, None)
    for d in defs:
        TOOL_NAME_MAP.pop(d.get("name", ""), None)

    logger.info("Unregistered generated tool '%s'", tool_id)


def load_all_generated_tools() -> None:
    """Load all active generated tools from the store into the runtime catalog.

    Called once at startup (after store initialization).
    """
    from app.services.generated_tool_store import generated_tool_store
    if not generated_tool_store.is_ready:
        return

    tools = generated_tool_store.list_active_tools()
    for doc in tools:
        try:
            _register_generated_tool(doc)
        except Exception:
            logger.exception("Failed to register generated tool %s", doc.get("tool_id"))

    if tools:
        logger.info("Loaded %d agent-generated tools from store", len(tools))


# ── Sandboxed execution ────────────────────────────────────────

def _execute_generated_code(
    code: str, function_name: str, arguments: dict
) -> dict:
    """Execute agent-generated tool code in a restricted namespace."""
    import builtins as _builtins

    # Build a restricted builtins dict
    safe_builtins = {
        name: getattr(_builtins, name)
        for name in [
            "True", "False", "None", "int", "float", "str", "bool",
            "list", "dict", "tuple", "set", "frozenset", "bytes", "bytearray",
            "len", "range", "enumerate", "zip", "map", "filter", "sorted",
            "reversed", "min", "max", "sum", "abs", "round", "pow", "divmod",
            "isinstance", "issubclass", "type", "hasattr", "getattr", "setattr",
            "repr", "print", "format", "chr", "ord", "hex", "oct", "bin",
            "all", "any", "iter", "next",
            "ValueError", "TypeError", "KeyError", "IndexError",
            "RuntimeError", "Exception", "StopIteration", "AttributeError",
        ]
        if hasattr(_builtins, name)
    }

    def _safe_import(name, *args, **kwargs):
        top = name.split(".")[0]
        if name not in ALLOWED_IMPORTS and top not in {
            m.split(".")[0] for m in ALLOWED_IMPORTS
        }:
            raise ImportError(f"Import '{name}' is not allowed in generated tools.")
        return __import__(name, *args, **kwargs)

    safe_builtins["__import__"] = _safe_import

    namespace: dict[str, Any] = {"__builtins__": safe_builtins}

    # Execute the module code
    exec(compile(code, "<generated_tool>", "exec"), namespace)  # noqa: S102

    execute_fn = namespace.get("execute_tool")
    if not callable(execute_fn):
        raise RuntimeError("Generated code does not define a callable `execute_tool`.")

    result = execute_fn(function_name, arguments)
    if not isinstance(result, dict):
        result = {"result": result}
    return result


def execute_generated_tool(
    tool_name: str,
    arguments: str | dict,
    tool_id: str,
    **kwargs,
) -> dict[str, Any]:
    """Execute a generated tool by looking up its code and running it sandboxed."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = {}

    from app.services.generated_tool_store import generated_tool_store
    doc = generated_tool_store.get_tool_by_tool_id(tool_id)
    if not doc:
        return {"success": False, "error": f"Generated tool '{tool_id}' not found."}
    if not doc.get("active", False):
        return {"success": False, "error": f"Generated tool '{tool_id}' is deactivated."}

    try:
        return _execute_generated_code(doc["code"], tool_name, arguments)
    except Exception as e:
        logger.exception("Generated tool '%s' failed", tool_id)
        return {"success": False, "error": str(e)}
