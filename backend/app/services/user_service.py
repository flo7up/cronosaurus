"""
User data service backed by Azure Cosmos DB.

Cosmos DB layout:
    Database:  cronosaurus
  Container: users   (partition key: /id)

Each user document looks like:
{
    "id": "1",                          # user id (string)
    "selected_model": "gpt-4.1-mini",   # last selected model
    "mcp_servers": [ ... ],
    "triggers": [
        {
            "id": "uuid",
            "conversation_id": "conv-uuid",
            "thread_id": "foundry-thread-id",
            "model": "gpt-4.1-mini",
            "type": "regular",
            "interval_minutes": 30,
            "prompt": "Check my emails and summarize",
            "description": "Email check",
            "active": true,
            "last_run": null,
            "next_run": "2026-02-26T10:30:00+00:00",
            "created_at": "2026-02-26T10:00:00+00:00",
            "run_count": 0
        }
    ]
}
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.config import settings
from app.tools.email_encryption import encrypt, decrypt

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "1"
CONTAINER_NAME = "users"


class UserService:
    def __init__(self):
        self._client: CosmosClient | None = None
        self._container = None
        self._initialized = False

    def initialize(self):
        """Connect to Cosmos DB and ensure database + container exist."""
        self.reset()

        if not settings.cosmos_url or not settings.cosmos_key:
            logger.warning(
                "COSMOS_URL / COSMOS_KEY not set - user service unavailable."
            )
            return

        try:
            self._client = CosmosClient(settings.cosmos_url, settings.cosmos_key)
            db = self._client.create_database_if_not_exists(settings.cosmos_db)
            self._container = db.create_container_if_not_exists(
                id=CONTAINER_NAME,
                partition_key=PartitionKey(path="/id"),
            )
            self._initialized = True
            # Ensure the default user document exists
            self._ensure_user(DEFAULT_USER_ID)
            logger.info("User service initialized (db=%s)", settings.cosmos_db)
        except Exception as e:
            logger.error("Failed to initialize user service: %s", e)
            raise

    def reset(self):
        """Drop cached clients so the service can be reinitialized safely."""
        self._client = None
        self._container = None
        self._initialized = False

    @property
    def is_ready(self) -> bool:
        return self._initialized

    # ── Helpers ──────────────────────────────────────────────────────

    def _ensure_user(self, user_id: str) -> dict:
        """Return the user doc, creating a blank one if it doesn't exist."""
        try:
            doc = self._container.read_item(user_id, partition_key=user_id)
            # Ensure triggers field exists (migration for existing docs)
            if "triggers" not in doc:
                doc["triggers"] = []
                self._upsert_user(doc)
            return doc
        except CosmosResourceNotFoundError:
            doc = {
                "id": user_id,
                "selected_model": "gpt-4.1-mini",
                "mcp_servers": [],
                "triggers": [],
            }
            self._container.create_item(doc)
            logger.info("Created default user document for user %s", user_id)
            return doc

    def _get_user(self, user_id: str = DEFAULT_USER_ID) -> dict:
        return self._container.read_item(user_id, partition_key=user_id)

    def _upsert_user(self, doc: dict) -> dict:
        return self._container.upsert_item(doc)

    # ── Model preference ─────────────────────────────────────────────

    def get_selected_model(self, user_id: str = DEFAULT_USER_ID) -> str:
        doc = self._get_user(user_id)
        return doc.get("selected_model", "gpt-4.1-mini")

    def set_selected_model(self, model: str, user_id: str = DEFAULT_USER_ID) -> str:
        doc = self._get_user(user_id)
        doc["selected_model"] = model
        self._upsert_user(doc)
        logger.info("User %s model set to %s", user_id, model)
        return model

    # ── Tool preferences ─────────────────────────────────────────────

    def get_tool_preferences(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        doc = self._get_user(user_id)
        return doc.get("tool_preferences", [])

    def set_tool_preference(
        self, tool_id: str, enabled: bool, user_id: str = DEFAULT_USER_ID
    ) -> list[dict]:
        doc = self._get_user(user_id)
        prefs = doc.setdefault("tool_preferences", [])
        # Update existing or add new
        for p in prefs:
            if p["id"] == tool_id:
                p["enabled"] = enabled
                break
        else:
            prefs.append({"id": tool_id, "enabled": enabled})
        self._upsert_user(doc)
        logger.info("Tool %s set to enabled=%s for user %s", tool_id, enabled, user_id)
        return prefs

    # ── MCP Servers ──────────────────────────────────────────────────

    def list_mcp_servers(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        doc = self._get_user(user_id)
        return doc.get("mcp_servers", [])

    def add_mcp_server(
        self,
        name: str,
        url: str,
        api_key: str = "",
        description: str = "",
        active: bool = True,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        doc = self._get_user(user_id)
        server = {
            "id": str(uuid.uuid4()),
            "name": name,
            "url": url,
            "api_key": api_key,
            "description": description,
            "active": active,
        }
        doc.setdefault("mcp_servers", []).append(server)
        self._upsert_user(doc)
        logger.info("MCP server '%s' added for user %s", name, user_id)
        return server

    def update_mcp_server(
        self,
        server_id: str,
        updates: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        doc = self._get_user(user_id)
        servers = doc.get("mcp_servers", [])
        for srv in servers:
            if srv["id"] == server_id:
                for k, v in updates.items():
                    if k != "id":  # never change id
                        srv[k] = v
                self._upsert_user(doc)
                logger.info("MCP server %s updated for user %s", server_id, user_id)
                return srv
        return None

    def delete_mcp_server(
        self,
        server_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        doc = self._get_user(user_id)
        servers = doc.get("mcp_servers", [])
        new_servers = [s for s in servers if s["id"] != server_id]
        if len(new_servers) == len(servers):
            return False
        doc["mcp_servers"] = new_servers
        self._upsert_user(doc)
        logger.info("MCP server %s deleted for user %s", server_id, user_id)
        return True

    def toggle_mcp_server(
        self,
        server_id: str,
        active: bool,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        return self.update_mcp_server(server_id, {"active": active}, user_id)

    # ── Triggers ─────────────────────────────────────────────────────

    MIN_INTERVAL_MINUTES = 1

    def list_triggers(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        doc = self._get_user(user_id)
        return doc.get("triggers", [])

    def get_trigger(self, trigger_id: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
        doc = self._get_user(user_id)
        for t in doc.get("triggers", []):
            if t["id"] == trigger_id:
                return t
        return None

    def get_trigger_for_conversation(
        self, conversation_id: str, user_id: str = DEFAULT_USER_ID
    ) -> dict | None:
        """Return the trigger for a conversation (at most one per conversation)."""
        doc = self._get_user(user_id)
        for t in doc.get("triggers", []):
            if t["conversation_id"] == conversation_id:
                return t
        return None

    def add_trigger(
        self,
        conversation_id: str,
        thread_id: str,
        model: str,
        interval_minutes: int,
        prompt: str,
        description: str = "",
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        if interval_minutes < self.MIN_INTERVAL_MINUTES:
            raise ValueError(
                f"Interval must be >= {self.MIN_INTERVAL_MINUTES} minutes"
            )

        doc = self._get_user(user_id)
        triggers = doc.get("triggers", [])

        # Enforce one trigger per conversation
        existing = [t for t in triggers if t["conversation_id"] == conversation_id]
        if existing:
            raise ValueError(
                f"Conversation {conversation_id} already has a trigger. "
                "Delete or update the existing one."
            )

        now = datetime.now(timezone.utc)
        trigger = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "model": model,
            "type": "regular",
            "interval_minutes": interval_minutes,
            "prompt": prompt,
            "description": description,
            "active": True,
            "last_run": None,
            "next_run": (now + timedelta(minutes=interval_minutes)).isoformat(),
            "created_at": now.isoformat(),
            "run_count": 0,
        }
        triggers.append(trigger)
        doc["triggers"] = triggers
        self._upsert_user(doc)
        logger.info(
            "Trigger created for conv %s: every %d min, desc=%s",
            conversation_id,
            interval_minutes,
            description,
        )
        return trigger

    def update_trigger(
        self,
        trigger_id: str,
        updates: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        if "interval_minutes" in updates:
            if updates["interval_minutes"] < self.MIN_INTERVAL_MINUTES:
                raise ValueError(
                    f"Interval must be >= {self.MIN_INTERVAL_MINUTES} minutes"
                )

        doc = self._get_user(user_id)
        triggers = doc.get("triggers", [])
        for t in triggers:
            if t["id"] == trigger_id:
                for k, v in updates.items():
                    if k not in ("id", "conversation_id", "thread_id", "created_at"):
                        t[k] = v
                # Recalculate next_run if interval changed and trigger is active
                if "interval_minutes" in updates and t.get("active"):
                    now = datetime.now(timezone.utc)
                    t["next_run"] = (
                        now + timedelta(minutes=t["interval_minutes"])
                    ).isoformat()
                self._upsert_user(doc)
                logger.info("Trigger %s updated", trigger_id)
                return t
        return None

    def delete_trigger(
        self,
        trigger_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        doc = self._get_user(user_id)
        triggers = doc.get("triggers", [])
        new_triggers = [t for t in triggers if t["id"] != trigger_id]
        if len(new_triggers) == len(triggers):
            return False
        doc["triggers"] = new_triggers
        self._upsert_user(doc)
        logger.info("Trigger %s deleted", trigger_id)
        return True

    def toggle_trigger(
        self,
        trigger_id: str,
        active: bool,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        doc = self._get_user(user_id)
        triggers = doc.get("triggers", [])
        for t in triggers:
            if t["id"] == trigger_id:
                t["active"] = active
                if active:
                    now = datetime.now(timezone.utc)
                    t["next_run"] = (
                        now + timedelta(minutes=t["interval_minutes"])
                    ).isoformat()
                else:
                    t["next_run"] = None
                self._upsert_user(doc)
                logger.info(
                    "Trigger %s %s",
                    trigger_id,
                    "activated" if active else "deactivated",
                )
                return t
        return None

    def get_due_triggers(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        """Return active triggers whose next_run is in the past."""
        doc = self._get_user(user_id)
        now = datetime.now(timezone.utc)
        due = []
        for t in doc.get("triggers", []):
            if not t.get("active") or not t.get("next_run"):
                continue
            try:
                next_run = datetime.fromisoformat(t["next_run"])
                if next_run <= now:
                    due.append(t)
            except (ValueError, TypeError):
                continue
        return due

    def update_trigger_after_run(
        self,
        trigger_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Mark a trigger as just-run: update last_run, next_run, run_count."""
        doc = self._get_user(user_id)
        triggers = doc.get("triggers", [])
        now = datetime.now(timezone.utc)
        for t in triggers:
            if t["id"] == trigger_id:
                t["last_run"] = now.isoformat()
                t["run_count"] = t.get("run_count", 0) + 1
                t["next_run"] = (
                    now + timedelta(minutes=t["interval_minutes"])
                ).isoformat()
                self._upsert_user(doc)
                logger.info(
                    "Trigger %s run #%d complete, next at %s",
                    trigger_id,
                    t["run_count"],
                    t["next_run"],
                )
                return t
        return None

    # ── Tool Library ────────────────────────────────────────────────

    # The default tool library matches all keys in the TOOL_CATALOG
    _DEFAULT_TOOL_LIBRARY = ["crypto", "stock", "email_send", "email_read", "triggers", "notifications"]

    def get_tool_library(self, user_id: str = DEFAULT_USER_ID) -> list[str]:
        """Return the list of tool IDs the user has in their library."""
        doc = self._get_user(user_id)
        return doc.get("tool_library", list(self._DEFAULT_TOOL_LIBRARY))

    def update_tool_library(
        self,
        tool_id: str,
        action: str,  # "add" or "remove"
        user_id: str = DEFAULT_USER_ID,
    ) -> list[str]:
        """Add or remove a tool from the user's library."""
        doc = self._get_user(user_id)
        library = doc.get("tool_library", list(self._DEFAULT_TOOL_LIBRARY))

        if action == "add" and tool_id not in library:
            library.append(tool_id)
        elif action == "remove" and tool_id in library:
            library.remove(tool_id)

        doc["tool_library"] = library
        self._upsert_user(doc)
        logger.info("Tool library updated: %s %s (user %s)", action, tool_id, user_id)
        return library

    def batch_update_tool_library(
        self,
        updates: list,
        user_id: str = DEFAULT_USER_ID,
    ) -> list[str]:
        """Apply multiple add/remove operations in one Cosmos write."""
        doc = self._get_user(user_id)
        library = doc.get("tool_library", list(self._DEFAULT_TOOL_LIBRARY))
        for u in updates:
            if u.action == "add" and u.tool_id not in library:
                library.append(u.tool_id)
            elif u.action == "remove" and u.tool_id in library:
                library.remove(u.tool_id)
        doc["tool_library"] = library
        self._upsert_user(doc)
        logger.info("Tool library batch updated: %d changes (user %s)", len(updates), user_id)
        return library

    # ── Email Accounts (multi-account) ─────────────────────────────

    def _migrate_email_account(self, doc: dict) -> bool:
        """Auto-migrate old single email_account to email_accounts array."""
        if "email_account" in doc and "email_accounts" not in doc:
            old = doc.pop("email_account")
            old["id"] = str(uuid.uuid4())
            old["label"] = old.get("label", old.get("from_email", "Default"))
            old["is_default"] = True
            doc["email_accounts"] = [old]
            self._upsert_user(doc)
            logger.info("Migrated single email_account to email_accounts array")
            return True
        return False

    def _get_email_accounts_raw(self, user_id: str = DEFAULT_USER_ID) -> tuple[dict, list[dict]]:
        """Return (user_doc, accounts_list), auto-migrating if needed."""
        doc = self._get_user(user_id)
        self._migrate_email_account(doc)
        return doc, doc.get("email_accounts", [])

    def list_email_accounts(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        """Return all email accounts (with encrypted password)."""
        _, accounts = self._get_email_accounts_raw(user_id)
        return accounts

    def list_email_accounts_safe(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        """Return all email accounts WITHOUT encrypted passwords."""
        accounts = self.list_email_accounts(user_id)
        return [self._account_to_safe(a) for a in accounts]

    def _account_to_safe(self, account: dict) -> dict:
        return {
            "id": account["id"],
            "label": account.get("label", ""),
            "smtp_host": account["smtp_host"],
            "smtp_port": account["smtp_port"],
            "username": account["username"],
            "from_email": account["from_email"],
            "from_name": account.get("from_name", ""),
            "use_tls": account.get("use_tls", True),
            "imap_host": account.get("imap_host", ""),
            "imap_port": account.get("imap_port", 993),
            "is_default": account.get("is_default", False),
            "configured": True,
            "has_password": bool(account.get("password_encrypted")),
        }

    def get_email_account(self, user_id: str = DEFAULT_USER_ID, account_id: str | None = None) -> dict | None:
        """Return a specific account by ID, or the default account, or None."""
        accounts = self.list_email_accounts(user_id)
        if not accounts:
            return None
        if account_id:
            for a in accounts:
                if a["id"] == account_id:
                    return a
            return None
        # Return default, or first
        for a in accounts:
            if a.get("is_default"):
                return a
        return accounts[0]

    def get_email_account_safe(self, user_id: str = DEFAULT_USER_ID, account_id: str | None = None) -> dict | None:
        """Return email account info WITHOUT the encrypted password."""
        account = self.get_email_account(user_id, account_id)
        if not account:
            return None
        return self._account_to_safe(account)

    def add_email_account(
        self,
        *,
        label: str = "",
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str = "",
        use_tls: bool = True,
        imap_host: str = "",
        imap_port: int = 993,
        is_default: bool = False,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        """Add a new email account. Returns safe response."""
        doc, accounts = self._get_email_accounts_raw(user_id)

        new_id = str(uuid.uuid4())
        # If this is the first account or marked default, ensure only one default
        if is_default or not accounts:
            for a in accounts:
                a["is_default"] = False
            is_default = True

        account = {
            "id": new_id,
            "label": label or from_email,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "username": username,
            "password_encrypted": encrypt(password) if password else "",
            "from_email": from_email,
            "from_name": from_name,
            "use_tls": use_tls,
            "imap_host": imap_host,
            "imap_port": imap_port,
            "is_default": is_default,
        }
        accounts.append(account)
        doc["email_accounts"] = accounts
        self._upsert_user(doc)
        logger.info("Email account added: id=%s label=%s for user %s", new_id, account["label"], user_id)
        return self._account_to_safe(account)

    def update_email_account(
        self,
        account_id: str,
        updates: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> dict | None:
        """Update a specific email account by ID. Re-encrypts password if provided."""
        doc, accounts = self._get_email_accounts_raw(user_id)
        for a in accounts:
            if a["id"] == account_id:
                # Handle is_default: ensure only one default
                if updates.get("is_default"):
                    for other in accounts:
                        other["is_default"] = False

                for k, v in updates.items():
                    if k == "password":
                        if v:  # only update if non-empty
                            a["password_encrypted"] = encrypt(v)
                    elif k not in ("id", "password_encrypted"):
                        a[k] = v

                doc["email_accounts"] = accounts
                self._upsert_user(doc)
                logger.info("Email account %s updated", account_id)
                return self._account_to_safe(a)
        return None

    def delete_email_account(self, account_id: str, user_id: str = DEFAULT_USER_ID) -> bool:
        """Remove a specific email account by ID."""
        doc, accounts = self._get_email_accounts_raw(user_id)
        new_accounts = [a for a in accounts if a["id"] != account_id]
        if len(new_accounts) == len(accounts):
            return False
        # If we deleted the default, make the first remaining one default
        if new_accounts and not any(a.get("is_default") for a in new_accounts):
            new_accounts[0]["is_default"] = True
        doc["email_accounts"] = new_accounts
        self._upsert_user(doc)
        logger.info("Email account %s deleted for user %s", account_id, user_id)
        return True

    def test_email_account(self, account_id: str | None = None, user_id: str = DEFAULT_USER_ID) -> dict:
        """Test the SMTP (and optionally IMAP) connection for a specific account."""
        import smtplib
        import imaplib
        account = self.get_email_account(user_id, account_id)
        if not account:
            return {"success": False, "error": "No email account configured."}

        password = None
        try:
            password = decrypt(account["password_encrypted"])
        except Exception:
            return {"success": False, "error": "Failed to decrypt email credentials."}

        # ── Test SMTP ──
        try:
            host = account["smtp_host"]
            port = int(account["smtp_port"])
            use_tls = account.get("use_tls", True)
            logger.info("Testing SMTP: host=%s port=%d use_tls=%s", host, port, use_tls)

            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=15)
            elif use_tls:
                server = smtplib.SMTP(host, port, timeout=15)
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP(host, port, timeout=15)
                server.ehlo()

            server.login(account["username"], password)
            server.quit()
        except smtplib.SMTPAuthenticationError:
            return {"success": False, "error": "SMTP authentication failed. Check username/password."}
        except smtplib.SMTPException as e:
            return {"success": False, "error": f"SMTP error: {e}"}
        except Exception as e:
            return {"success": False, "error": f"SMTP connection failed: {e}"}

        # ── Test IMAP (if configured) ──
        imap_host = account.get("imap_host")
        imap_port = int(account.get("imap_port", 993))
        if imap_host:
            try:
                logger.info("Testing IMAP: host=%s port=%d", imap_host, imap_port)
                conn = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=15)
                conn.login(account["username"], password)
                conn.logout()
            except imaplib.IMAP4.error as e:
                return {"success": False, "error": f"SMTP OK, but IMAP auth failed: {e}"}
            except Exception as e:
                return {"success": False, "error": f"SMTP OK, but IMAP connection failed: {e}"}

        msg = "SMTP connection successful."
        if imap_host:
            msg = "SMTP and IMAP connections successful."
        return {"success": True, "message": msg}

    def send_test_email(self, to_email: str, account_id: str | None = None, user_id: str = DEFAULT_USER_ID, use_port: int = 0) -> dict:
        """Send an actual test email and return full SMTP debug transcript.
        
        If use_port is given, override the stored port (useful for testing 587 vs 465).
        """
        import smtplib
        import io
        import sys
        from email.mime.text import MIMEText
        from email.utils import formatdate, formataddr, make_msgid

        account = self.get_email_account(user_id, account_id)
        if not account:
            return {"success": False, "error": "No email account configured."}
        try:
            password = decrypt(account["password_encrypted"])
            host = account["smtp_host"]
            port = use_port if use_port else int(account["smtp_port"])
            username = account["username"]
            from_email = account["from_email"]
            from_name = account.get("from_name", "")
            domain = from_email.split("@")[-1] if "@" in from_email else "localhost"

            # Build a simple ASCII-only test message (avoid base64 encoding
            # which some outbound spam filters flag).
            body_text = (
                "This is a test email from Cronosaurus.\r\n"
                "\r\n"
                "If you received this, your email configuration is working correctly.\r\n"
                "\r\n"
                f"SMTP server: {host}:{port}\r\n"
                f"From: {from_email}\r\n"
                f"Sent at: {formatdate(localtime=True)}\r\n"
            )
            # Use us-ascii charset to get 7bit CTE instead of base64
            msg = MIMEText(body_text, "plain", "us-ascii")

            msg["Subject"] = f"Cronosaurus test email"
            msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
            msg["To"] = to_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=domain)
            msg["Reply-To"] = from_email

            logger.info("Sending test email: from=%s to=%s host=%s:%d", from_email, to_email, host, port)

            # Capture SMTP debug — redirect stderr BEFORE creating server
            # so we also capture the initial EHLO exchange
            debug_buf = io.StringIO()
            old_stderr = sys.stderr
            sys.stderr = debug_buf

            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=30)
                server.set_debuglevel(2)
            elif port == 587:
                server = smtplib.SMTP(host, port, timeout=30)
                server.set_debuglevel(2)
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP(host, port, timeout=30)
                server.set_debuglevel(2)
                server.ehlo()

            server.login(username, password)
            refused = server.sendmail(from_email, [to_email], msg.as_string())
            server.quit()

            sys.stderr = old_stderr
            smtp_log = debug_buf.getvalue()

            if smtp_log:
                logger.info("SMTP test send transcript:\n%s", smtp_log)

            if refused:
                return {
                    "success": False,
                    "error": f"Refused: {refused}",
                    "smtp_log": smtp_log[-2000:] if len(smtp_log) > 2000 else smtp_log,
                }

            return {
                "success": True,
                "message": f"Test email sent to {to_email}",
                "message_id": msg["Message-ID"],
                "smtp_log": smtp_log[-2000:] if len(smtp_log) > 2000 else smtp_log,
            }
        except smtplib.SMTPRecipientsRefused as e:
            sys.stderr = old_stderr
            return {"success": False, "error": f"Recipients refused: {e.recipients}"}
        except smtplib.SMTPDataError as e:
            sys.stderr = old_stderr
            return {"success": False, "error": f"Server rejected message data: {e.smtp_code} {e.smtp_error}"}
        except smtplib.SMTPException as e:
            sys.stderr = old_stderr
            return {"success": False, "error": f"SMTP error: {e}"}
        except Exception as e:
            try:
                sys.stderr = old_stderr
            except Exception:
                pass
            return {"success": False, "error": f"Failed: {e}"}


    # ── Notification preferences ──────────────────────────────────────

    def get_notification_preferences(self, user_id: str = DEFAULT_USER_ID) -> dict:
        """Get user notification delivery preferences."""
        if not self._initialized:
            return {"delivery": "all"}
        doc = self._get_user(user_id)
        return doc.get("notification_preferences", {"delivery": "all"})

    def update_notification_preferences(self, prefs: dict, user_id: str = DEFAULT_USER_ID) -> dict:
        """Update user notification delivery preferences."""
        doc = self._get_user(user_id)
        doc["notification_preferences"] = prefs
        self._upsert_user(doc)
        return prefs


user_service = UserService()
