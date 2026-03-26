"""
SQLite-backed local storage — drop-in replacement for Cosmos DB.

Used automatically when COSMOS_URL is not configured. Provides the same
document-oriented API that the four Cosmos-backed services expect:
  - users    (single JSON document per user, partition key: id)
  - agents   (JSON document per agent, partition key: user_id)
  - messages (structured rows, partition key: thread_id)
  - notifications (structured rows, partition key: user_id)

All data stored in backend/data/cronosaurus.db (auto-created).
"""

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DB_DIR / "cronosaurus.db"

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return _local.conn


def _init_tables():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '1',
            data TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_agents_user ON agents(user_id);

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            ts TEXT NOT NULL DEFAULT '',
            images TEXT,
            tool_steps TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, ts);

        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '1',
            data TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);

        CREATE TABLE IF NOT EXISTS generated_tools (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '1',
            data TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_generated_tools_user ON generated_tools(user_id);
    """)
    conn.commit()
    logger.info("Local SQLite store initialized at %s", DB_PATH)


# ══════════════════════════════════════════════════════════
#  Container-like wrapper (mimics Cosmos container API)
# ══════════════════════════════════════════════════════════


class LocalContainer:
    """A thin wrapper around a SQLite table that provides the same
    read/create/upsert/replace/delete/query API as a Cosmos container."""

    def __init__(self, table: str, partition_key_field: str = "id"):
        self._table = table
        self._pk_field = partition_key_field
        # Tables that store full documents as JSON blobs
        self._is_doc_table = table in ("users", "agents", "notifications", "generated_tools")

    # ── Single-item operations ───────────────────────────────

    def read_item(self, item: str, partition_key: str = "") -> dict:
        """Read a single item by ID. Raises CosmosResourceNotFoundError equivalent."""
        conn = _get_conn()
        row = conn.execute(
            f"SELECT * FROM {self._table} WHERE id = ?", (item,)
        ).fetchone()
        if not row:
            from azure.cosmos.exceptions import CosmosResourceNotFoundError
            raise CosmosResourceNotFoundError(
                status_code=404, message=f"Item {item} not found"
            )
        return self._row_to_doc(row)

    def create_item(self, body: dict) -> dict:
        """Insert a new item."""
        conn = _get_conn()
        doc_id = body.get("id", "")
        if self._is_doc_table:
            if self._table == "agents":
                conn.execute(
                    "INSERT INTO agents (id, user_id, data, created_at) VALUES (?, ?, ?, ?)",
                    (doc_id, body.get("user_id", "1"), json.dumps(body), body.get("created_at", "")),
                )
            elif self._table == "notifications":
                conn.execute(
                    "INSERT INTO notifications (id, user_id, data) VALUES (?, ?, ?)",
                    (doc_id, body.get("user_id", "1"), json.dumps(body)),
                )
            elif self._table == "generated_tools":
                conn.execute(
                    "INSERT INTO generated_tools (id, user_id, data, created_at) VALUES (?, ?, ?, ?)",
                    (doc_id, body.get("user_id", "1"), json.dumps(body), body.get("created_at", "")),
                )
            else:  # users
                conn.execute(
                    "INSERT INTO users (id, data) VALUES (?, ?)",
                    (doc_id, json.dumps(body)),
                )
        else:  # messages
            conn.execute(
                "INSERT INTO messages (id, thread_id, role, content, ts, images, tool_steps) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    body.get("thread_id", ""),
                    body.get("role", ""),
                    body.get("content", ""),
                    body.get("ts", ""),
                    json.dumps(body["images"]) if body.get("images") else None,
                    json.dumps(body["tool_steps"]) if body.get("tool_steps") else None,
                ),
            )
        conn.commit()
        return body

    def upsert_item(self, body: dict) -> dict:
        """Insert or replace an item."""
        conn = _get_conn()
        doc_id = body.get("id", "")
        if self._is_doc_table:
            if self._table == "agents":
                conn.execute(
                    "INSERT OR REPLACE INTO agents (id, user_id, data, created_at) VALUES (?, ?, ?, ?)",
                    (doc_id, body.get("user_id", "1"), json.dumps(body), body.get("created_at", "")),
                )
            elif self._table == "notifications":
                conn.execute(
                    "INSERT OR REPLACE INTO notifications (id, user_id, data) VALUES (?, ?, ?)",
                    (doc_id, body.get("user_id", "1"), json.dumps(body)),
                )
            elif self._table == "generated_tools":
                conn.execute(
                    "INSERT OR REPLACE INTO generated_tools (id, user_id, data, created_at) VALUES (?, ?, ?, ?)",
                    (doc_id, body.get("user_id", "1"), json.dumps(body), body.get("created_at", "")),
                )
            else:  # users
                conn.execute(
                    "INSERT OR REPLACE INTO users (id, data) VALUES (?, ?)",
                    (doc_id, json.dumps(body)),
                )
        else:  # messages
            conn.execute(
                "INSERT OR REPLACE INTO messages (id, thread_id, role, content, ts, images, tool_steps) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    doc_id,
                    body.get("thread_id", ""),
                    body.get("role", ""),
                    body.get("content", ""),
                    body.get("ts", ""),
                    json.dumps(body["images"]) if body.get("images") else None,
                    json.dumps(body["tool_steps"]) if body.get("tool_steps") else None,
                ),
            )
        conn.commit()
        return body

    def replace_item(self, item: dict, body: dict) -> dict:
        """Replace an existing item (same as upsert for SQLite)."""
        return self.upsert_item(body)

    def delete_item(self, item: str, partition_key: str = "") -> None:
        """Delete an item by ID."""
        conn = _get_conn()
        cursor = conn.execute(f"DELETE FROM {self._table} WHERE id = ?", (item,))
        conn.commit()
        if cursor.rowcount == 0:
            from azure.cosmos.exceptions import CosmosResourceNotFoundError
            raise CosmosResourceNotFoundError(
                status_code=404, message=f"Item {item} not found"
            )

    # ── Query operations ─────────────────────────────────────

    def query_items(
        self,
        query: str,
        parameters: list[dict] | None = None,
        partition_key: str = "",
        enable_cross_partition_query: bool = False,
    ) -> list[dict]:
        """Execute a Cosmos-SQL-like query. Translates common patterns to SQLite SQL."""
        conn = _get_conn()
        sql, params = _translate_cosmos_query(query, parameters or [], self._table, self._is_doc_table)
        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_doc(row) for row in rows]

    # ── Helpers ──────────────────────────────────────────────

    def _row_to_doc(self, row: sqlite3.Row) -> dict:
        """Convert a SQLite row to a document dict."""
        if self._is_doc_table:
            return json.loads(row["data"])
        else:
            # messages table — structured
            doc: dict = {
                "id": row["id"],
                "thread_id": row["thread_id"],
                "role": row["role"],
                "content": row["content"],
                "ts": row["ts"],
            }
            if row["images"]:
                doc["images"] = json.loads(row["images"])
            if row["tool_steps"]:
                doc["tool_steps"] = json.loads(row["tool_steps"])
            return doc


def _translate_cosmos_query(
    cosmos_sql: str,
    parameters: list[dict],
    table: str,
    is_doc_table: bool,
) -> tuple[str, list]:
    """Translate a Cosmos SQL query to SQLite SQL.

    Handles the common Cosmos SQL patterns used in this codebase:
    - SELECT * FROM c WHERE c.field = @param
    - SELECT c.field1, c.field2 FROM c WHERE ...
    - SELECT VALUE COUNT(1) FROM c WHERE ...
    - ORDER BY c.field ASC/DESC
    - OFFSET n LIMIT m
    """
    import re

    sql = cosmos_sql.strip()

    # Build parameter map: @name -> value
    param_map = {p["name"]: p["value"] for p in parameters}

    # Handle SELECT VALUE COUNT(1) → SELECT COUNT(1)
    is_count = "SELECT VALUE COUNT" in sql.upper()

    if is_doc_table:
        # For doc tables, we always SELECT data and parse JSON in Python
        # But we need to translate WHERE clauses to use json_extract

        # Extract WHERE clause
        where_match = re.search(r'WHERE\s+(.+?)(?:\s+ORDER\s+|\s+OFFSET\s+|$)', sql, re.IGNORECASE)
        where_parts = []
        sqlite_params = []

        if where_match:
            where_str = where_match.group(1).strip()
            # Split on AND
            conditions = re.split(r'\s+AND\s+', where_str, flags=re.IGNORECASE)
            for cond in conditions:
                cond = cond.strip()
                # c.field = @param
                m = re.match(r'c\.(\w+)\s*=\s*(@\w+)', cond)
                if m:
                    field, param_name = m.group(1), m.group(2)
                    # For top-level indexed columns, use them directly
                    if field == "user_id" and table in ("agents", "notifications"):
                        where_parts.append(f"{field} = ?")
                    elif field == "id" and table == "users":
                        where_parts.append("id = ?")
                    else:
                        where_parts.append(f"json_extract(data, '$.{field}') = ?")
                    sqlite_params.append(param_map[param_name])
                    continue
                # c.field = false / true
                m = re.match(r'c\.(\w+)\s*=\s*(true|false)', cond, re.IGNORECASE)
                if m:
                    field = m.group(1)
                    val = m.group(2).lower() == "true"
                    where_parts.append(f"json_extract(data, '$.{field}') = ?")
                    sqlite_params.append(val)
                    continue
                # c.role IN ('user', 'assistant')
                m = re.match(r"c\.(\w+)\s+IN\s*\((.+?)\)", cond, re.IGNORECASE)
                if m:
                    field = m.group(1)
                    values = [v.strip().strip("'\"") for v in m.group(2).split(",")]
                    placeholders = ",".join("?" * len(values))
                    where_parts.append(f"json_extract(data, '$.{field}') IN ({placeholders})")
                    sqlite_params.extend(values)
                    continue

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"

        # Handle ORDER BY
        order_match = re.search(r'ORDER\s+BY\s+c\.(\w+)\s+(ASC|DESC)', sql, re.IGNORECASE)
        order_clause = ""
        if order_match:
            field, direction = order_match.group(1), order_match.group(2)
            if field == "created_at" and table == "agents":
                order_clause = f" ORDER BY created_at {direction}"
            else:
                order_clause = f" ORDER BY json_extract(data, '$.{field}') {direction}"

        # Handle LIMIT
        limit_match = re.search(r'LIMIT\s+(@\w+|\d+)', sql, re.IGNORECASE)
        limit_clause = ""
        if limit_match:
            limit_val = limit_match.group(1)
            if limit_val.startswith("@"):
                limit_clause = " LIMIT ?"
                sqlite_params.append(param_map[limit_val])
            else:
                limit_clause = f" LIMIT {limit_val}"

        if is_count:
            return f"SELECT COUNT(1) as cnt FROM {table} WHERE {where_clause}", sqlite_params
        else:
            return f"SELECT data FROM {table} WHERE {where_clause}{order_clause}{limit_clause}", sqlite_params

    else:
        # messages table — structured, translate directly
        # Replace c.field with field
        sql = re.sub(r'\bc\.(\w+)', r'\1', sql)
        # Replace FROM c with FROM messages
        sql = re.sub(r'\bFROM\s+c\b', f'FROM {table}', sql, flags=re.IGNORECASE)
        # Replace @params with ?
        sqlite_params = []
        for p in parameters:
            sql = sql.replace(p["name"], "?")
            sqlite_params.append(p["value"])
        # Handle SELECT VALUE COUNT
        if is_count:
            sql = re.sub(r'SELECT\s+VALUE\s+COUNT', 'SELECT COUNT', sql, flags=re.IGNORECASE)

        return sql, sqlite_params


# ══════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════

_initialized = False


def initialize():
    """Initialize the local SQLite store."""
    global _initialized
    _init_tables()
    _initialized = True


def is_ready() -> bool:
    return _initialized


def get_container(name: str) -> LocalContainer:
    """Get a container-like object for the given table name.

    Maps Cosmos container names to SQLite tables:
      users, agents, messages, notifications
    """
    pk_fields = {
        "users": "id",
        "agents": "user_id",
        "messages": "thread_id",
        "notifications": "user_id",
        "generated_tools": "user_id",
    }
    return LocalContainer(name, pk_fields.get(name, "id"))
