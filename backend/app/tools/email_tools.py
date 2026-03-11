"""
Function tool definitions for sending and reading emails.

Send: SMTP via user-configured account.
Read: IMAP via user-configured account (same credentials, separate host/port).
"""

import json
import logging
import smtplib
import imaplib
import email as email_lib
import uuid
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import formatdate, formataddr, make_msgid
from typing import Any

from app.tools.email_encryption import decrypt

logger = logging.getLogger(__name__)

# ── JSON-Schema definitions — Send ──────────────────────────────

EMAIL_SEND_TOOL_DEFINITIONS = [
    {
        "name": "send_email",
        "description": (
            "Send an email on behalf of the user using their configured SMTP email account. "
            "The user must have an email account set up in their settings before this tool can be used. "
            "Supports plain text and HTML content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": (
                        "Recipient email address(es). For multiple recipients, "
                        "separate with commas, e.g. 'alice@example.com, bob@example.com'."
                    ),
                },
                "subject": {
                    "type": "string",
                    "description": "The email subject line.",
                },
                "body": {
                    "type": "string",
                    "description": (
                        "The email body content. Can be plain text or HTML. "
                        "If you use HTML, include proper tags like <html><body>...</body></html>."
                    ),
                },
                "is_html": {
                    "type": "boolean",
                    "description": (
                        "Set to true if the body contains HTML markup. "
                        "Defaults to false (plain text)."
                    ),
                },
                "image_base64": {
                    "type": "string",
                    "description": (
                        "Base64-encoded image data to embed in the email. "
                        "The image will be attached inline. Use this to include "
                        "captured images (e.g. from Twitch stream captures)."
                    ),
                },
                "image_media_type": {
                    "type": "string",
                    "description": (
                        "MIME type of the image, e.g. 'image/jpeg' or 'image/png'. "
                        "Defaults to 'image/jpeg'."
                    ),
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
]

# ── JSON-Schema definitions — Read ──────────────────────────────

EMAIL_READ_TOOL_DEFINITIONS = [
    {
        "name": "read_inbox",
        "description": (
            "Read recent emails from the user's inbox via IMAP. "
            "Returns subject, sender, date and a short preview of each email."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of recent emails to fetch (default 10, max 50).",
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "If true, only return unread/unseen emails. Default false.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_email",
        "description": (
            "Read the full content of a specific email by its message number "
            "(returned from read_inbox or search_emails)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The email message number to read (from read_inbox results).",
                },
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "search_emails",
        "description": "Search emails by sender, subject, or keyword.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_address": {
                    "type": "string",
                    "description": "Filter by sender email address.",
                },
                "subject": {
                    "type": "string",
                    "description": "Filter by subject line keyword.",
                },
                "count": {
                    "type": "integer",
                    "description": "Maximum number of results (default 10).",
                },
            },
            "required": [],
        },
    },
]

# ── JSON-Schema definitions — Trigger email (read by UID) ───────

EMAIL_TRIGGER_TOOL_DEFINITIONS = [
    {
        "name": "read_trigger_email",
        "description": (
            "Read the full body of an email by its IMAP UID. "
            "Use this when you receive a Gmail push notification and need "
            "to inspect the full email content. The UID is provided in the "
            "notification."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "uid": {
                    "type": "integer",
                    "description": "The IMAP UID of the email (from the push notification).",
                },
            },
            "required": ["uid"],
        },
    },
]

# Legacy combined list (for backward compat if needed)
EMAIL_TOOL_DEFINITIONS = EMAIL_SEND_TOOL_DEFINITIONS + EMAIL_READ_TOOL_DEFINITIONS + EMAIL_TRIGGER_TOOL_DEFINITIONS

EMAIL_SEND_TOOL_NAMES = {t["name"] for t in EMAIL_SEND_TOOL_DEFINITIONS}
EMAIL_READ_TOOL_NAMES = {t["name"] for t in EMAIL_READ_TOOL_DEFINITIONS}
EMAIL_TRIGGER_TOOL_NAMES = {t["name"] for t in EMAIL_TRIGGER_TOOL_DEFINITIONS}
EMAIL_TOOL_NAMES = EMAIL_SEND_TOOL_NAMES | EMAIL_READ_TOOL_NAMES | EMAIL_TRIGGER_TOOL_NAMES


# ── Connection test helper ─────────────────────────────────────

def test_smtp_connection(
    *,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    use_tls: bool = True,
) -> dict[str, Any]:
    """Try to authenticate with the SMTP server without sending anything."""
    try:
        if int(smtp_port) == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        elif use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.ehlo()

        server.login(username, password)
        server.quit()
        return {"success": True, "message": "SMTP authentication successful."}
    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP test auth failed: %s", e)
        return {"success": False, "error": f"Authentication failed: {e.smtp_error.decode('utf-8', errors='replace') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)}"}
    except smtplib.SMTPException as e:
        logger.error("SMTP test error: %s", e)
        return {"success": False, "error": f"SMTP error: {e}"}
    except Exception as e:
        logger.error("SMTP test connection error: %s", e)
        return {"success": False, "error": f"Connection error: {e}"}


def test_email_connection(user_id: str = "1") -> dict[str, Any]:
    """Test the stored email account credentials."""
    account, err = _get_email_account(user_id)
    if err:
        return {"success": False, "error": err}

    password = account["_password"]
    logger.info(
        "Testing SMTP connection: host=%s port=%s user=%s password_len=%d",
        account["smtp_host"], account["smtp_port"], account["username"], len(password) if password else 0,
    )
    return test_smtp_connection(
        smtp_host=account["smtp_host"],
        smtp_port=account["smtp_port"],
        username=account["username"],
        password=password,
        use_tls=account.get("use_tls", True),
    )


# ── SMTP send helper ───────────────────────────────────────────

def _send_smtp(
    *,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    use_tls: bool,
    from_email: str,
    from_name: str,
    to: str,
    subject: str,
    body: str,
    is_html: bool = False,
    images: list[dict] | None = None,
) -> dict[str, Any]:
    """Actually send an email via SMTP. Returns a result dict.

    images: optional list of {"data": base64_str, "media_type": "image/jpeg"}
            Attached as inline CID images (cid:notif_img_0, cid:notif_img_1, ...).
    """
    import io

    try:
        # Determine charset: use us-ascii (7bit CTE) when possible to avoid
        # base64 encoding which some outbound spam filters flag.
        try:
            body.encode("ascii")
            charset = "us-ascii"
        except UnicodeEncodeError:
            charset = "utf-8"

        if is_html:
            if images:
                # Use mixed > related > alternative structure so images
                # appear both inline in HTML and as downloadable attachments.
                import base64
                from email.mime.image import MIMEImage

                msg = MIMEMultipart("mixed")
                related_part = MIMEMultipart("related")
                alt_part = MIMEMultipart("alternative")
                alt_part.attach(MIMEText(body, "plain", charset))
                alt_part.attach(MIMEText(body, "html", charset))
                related_part.attach(alt_part)

                for i, img in enumerate(images):
                    raw_b64 = img["data"]
                    raw_b64 += "=" * (-len(raw_b64) % 4)
                    img_data = base64.b64decode(raw_b64)
                    media_type = img.get("media_type", "image/jpeg")
                    subtype = media_type.split("/")[-1] if "/" in media_type else "jpeg"
                    filename = f"image_{i}.{subtype}"
                    cid = f"notif_img_{i}"

                    # Inline part (for CID references in HTML body)
                    inline_img = MIMEImage(img_data, _subtype=subtype)
                    inline_img.add_header("Content-ID", f"<{cid}>")
                    inline_img.add_header("Content-Disposition", "inline", filename=filename)
                    inline_img.add_header("X-Attachment-Id", cid)
                    related_part.attach(inline_img)

                    # Attachment part (shows as downloadable attachment)
                    attach_img = MIMEImage(img_data, _subtype=subtype)
                    attach_img.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(attach_img)

                # Insert the related part (HTML + inline images) before attachments
                msg._payload.insert(0, related_part)
            else:
                msg = MIMEMultipart("alternative")
                msg.attach(MIMEText(body, "plain", charset))
                msg.attach(MIMEText(body, "html", charset))
        else:
            msg = MIMEText(body, "plain", charset)

        # Use the sender's domain for Message-ID only (not for EHLO — using
        # the server's own domain as EHLO hostname causes auth rejection on
        # Gmail and other providers that check for domain spoofing).
        sender_domain = from_email.split("@")[-1] if "@" in from_email else smtp_host

        msg["Subject"] = subject
        msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
        msg["To"] = to
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=sender_domain)
        msg["Reply-To"] = from_email
        msg["X-Mailer"] = "Cronosaurus"

        # Capture SMTP debug output
        debug_stream = io.StringIO()

        if int(smtp_port) == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        elif use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.ehlo()

        # Enable debug to capture full SMTP conversation
        server.set_debuglevel(2)
        # Redirect debug to our logger
        import sys
        old_stderr = sys.stderr
        sys.stderr = debug_stream

        server.login(username, password)
        recipients = [addr.strip() for addr in to.split(",")]

        # Use send_message for better RFC compliance
        send_result = server.sendmail(from_email, recipients, msg.as_string())

        server.quit()

        # Restore stderr and log the SMTP conversation
        sys.stderr = old_stderr
        smtp_log = debug_stream.getvalue()
        if smtp_log:
            logger.info("SMTP debug log:\n%s", smtp_log)

        if send_result:
            logger.warning("Some recipients refused: %s", send_result)
            return {"success": False, "error": f"Server refused some recipients: {list(send_result.keys())}"}

        logger.info("Email sent to %s (subject: %s) via %s:%s", to, subject, smtp_host, smtp_port)
        logger.info("Message-ID: %s", msg["Message-ID"])
        return {"success": True, "message": f"Email sent successfully to {to}"}

    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP auth failed for user=%s host=%s port=%s: %s", username, smtp_host, smtp_port, e)
        hint = (
            "SMTP authentication failed. "
            "If you use Gmail with 2-Step Verification, you need an App Password "
            "(https://myaccount.google.com/apppasswords). "
            "Check your username and password in the Tools → Email Account panel."
        )
        return {"success": False, "error": hint}
    except smtplib.SMTPException as e:
        logger.error("SMTP error: %s", e)
        return {"success": False, "error": f"SMTP error: {e}"}
    except Exception as e:
        logger.error("Email send error: %s", e)
        return {"success": False, "error": f"Failed to send email: {e}"}


# ── IMAP read helpers ──────────────────────────────────────────

def _decode_header_value(raw: str | None) -> str:
    """Decode an email header that may be RFC 2047-encoded."""
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return " ".join(decoded)


def _get_text_from_message(msg: email_lib.message.Message) -> str:
    """Extract the plain-text body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # Fall back to HTML
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return f"[HTML] {payload.decode(charset, errors='replace')[:2000]}"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _connect_imap(imap_host: str, imap_port: int, username: str, password: str) -> imaplib.IMAP4_SSL:
    """Connect and authenticate to IMAP server."""
    conn = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30)
    conn.login(username, password)
    return conn


def _read_inbox(
    *,
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    count: int = 10,
    unread_only: bool = False,
) -> dict[str, Any]:
    """Fetch recent emails from INBOX."""
    try:
        conn = _connect_imap(imap_host, imap_port, username, password)
        conn.select("INBOX", readonly=True)

        criteria = "UNSEEN" if unread_only else "ALL"
        status, data = conn.search(None, criteria)
        if status != "OK":
            conn.logout()
            return {"success": False, "error": "Failed to search inbox."}

        msg_nums = data[0].split()
        if not msg_nums:
            conn.logout()
            return {"success": True, "emails": [], "total": 0}

        count = min(count, 50)
        recent = msg_nums[-count:]  # last N (most recent)
        recent.reverse()

        emails = []
        for num in recent:
            status, msg_data = conn.fetch(num, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email_lib.message_from_bytes(raw)
            body = _get_text_from_message(msg)
            emails.append({
                "id": num.decode(),
                "from": _decode_header_value(msg["From"]),
                "subject": _decode_header_value(msg["Subject"]),
                "date": msg["Date"] or "",
                "preview": body[:300].strip(),
            })

        conn.logout()
        return {"success": True, "emails": emails, "total": len(msg_nums)}

    except imaplib.IMAP4.error as e:
        logger.error("IMAP error: %s", e)
        return {"success": False, "error": f"IMAP error: {e}"}
    except Exception as e:
        logger.error("Email read error: %s", e)
        return {"success": False, "error": f"Failed to read emails: {e}"}


def _read_email_by_id(
    *,
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    email_id: str,
) -> dict[str, Any]:
    """Read the full content of a specific email by message number."""
    try:
        conn = _connect_imap(imap_host, imap_port, username, password)
        conn.select("INBOX", readonly=True)

        status, msg_data = conn.fetch(email_id.encode(), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            conn.logout()
            return {"success": False, "error": f"Email {email_id} not found."}

        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
        msg = email_lib.message_from_bytes(raw)
        body = _get_text_from_message(msg)

        conn.logout()
        return {
            "success": True,
            "email": {
                "id": email_id,
                "from": _decode_header_value(msg["From"]),
                "to": _decode_header_value(msg["To"]),
                "subject": _decode_header_value(msg["Subject"]),
                "date": msg["Date"] or "",
                "body": body[:5000],
            },
        }
    except Exception as e:
        logger.error("Read email error: %s", e)
        return {"success": False, "error": f"Failed to read email: {e}"}


def _read_email_by_uid(
    *,
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    uid: int,
) -> dict[str, Any]:
    """Read the full content of a specific email by IMAP UID."""
    try:
        conn = _connect_imap(imap_host, imap_port, username, password)
        conn.select("INBOX", readonly=True)

        status, msg_data = conn.uid("FETCH", str(uid).encode(), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            conn.logout()
            return {"success": False, "error": f"Email with UID {uid} not found."}

        raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
        msg = email_lib.message_from_bytes(raw)
        body = _get_text_from_message(msg)

        conn.logout()
        return {
            "success": True,
            "email": {
                "uid": uid,
                "from": _decode_header_value(msg["From"]),
                "to": _decode_header_value(msg["To"]),
                "subject": _decode_header_value(msg["Subject"]),
                "date": msg["Date"] or "",
                "body": body[:5000],
            },
        }
    except Exception as e:
        logger.error("Read email by UID error: %s", e)
        return {"success": False, "error": f"Failed to read email: {e}"}


def _search_emails(
    *,
    imap_host: str,
    imap_port: int,
    username: str,
    password: str,
    from_address: str = "",
    subject: str = "",
    count: int = 10,
) -> dict[str, Any]:
    """Search emails by from address or subject keyword."""
    try:
        conn = _connect_imap(imap_host, imap_port, username, password)
        conn.select("INBOX", readonly=True)

        criteria_parts = []
        if from_address:
            criteria_parts.append(f'FROM "{from_address}"')
        if subject:
            criteria_parts.append(f'SUBJECT "{subject}"')
        if not criteria_parts:
            criteria_parts.append("ALL")

        criteria = " ".join(criteria_parts) if len(criteria_parts) == 1 else f"({' '.join(criteria_parts)})"
        status, data = conn.search(None, criteria)
        if status != "OK":
            conn.logout()
            return {"success": False, "error": "Search failed."}

        msg_nums = data[0].split()
        count = min(count, 50)
        recent = msg_nums[-count:]
        recent.reverse()

        emails = []
        for num in recent:
            status, msg_data = conn.fetch(num, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email_lib.message_from_bytes(raw)
            body = _get_text_from_message(msg)
            emails.append({
                "id": num.decode(),
                "from": _decode_header_value(msg["From"]),
                "subject": _decode_header_value(msg["Subject"]),
                "date": msg["Date"] or "",
                "preview": body[:300].strip(),
            })

        conn.logout()
        return {"success": True, "emails": emails, "total": len(msg_nums)}
    except Exception as e:
        logger.error("Search emails error: %s", e)
        return {"success": False, "error": f"Failed to search emails: {e}"}


# ── Tool executor (called by agent_service) ────────────────────

def _get_email_account(user_id: str, account_id: str | None = None) -> tuple[dict | None, str | None]:
    """Fetch email account and decrypt password. Returns (account, password) or (None, error)."""
    from app.services.user_service import user_service

    account = user_service.get_email_account(user_id, account_id=account_id)
    if not account:
        msg = "No email account configured. The user needs to set up their email in the Tools panel first."
        if account_id:
            msg = f"Email account '{account_id}' not found. It may have been deleted."
        return None, msg
    try:
        password = decrypt(account["password_encrypted"])
        return {**account, "_password": password}, None
    except Exception as e:
        logger.error("Failed to decrypt email password: %s", e)
        return None, "Failed to decrypt email credentials."


def execute_email_tool(
    tool_name: str,
    arguments: str | dict,
    user_id: str = "1",
    account_id: str | None = None,
) -> dict[str, Any]:
    """Execute an email tool call (send or read)."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    account, err = _get_email_account(user_id, account_id=account_id)
    if err:
        return {"success": False, "error": err}

    password = account["_password"]
    logger.debug(
        "Email tool=%s user=%s smtp=%s:%s password_len=%d",
        tool_name,
        account["username"],
        account["smtp_host"],
        account["smtp_port"],
        len(password) if password else 0,
    )

    # ── Send tools ──
    if tool_name == "send_email":
        # Build inline images list if provided
        email_images = None
        img_b64 = arguments.get("image_base64", "")
        if img_b64:
            email_images = [{"data": img_b64, "media_type": arguments.get("image_media_type", "image/jpeg")}]

        email_body = arguments["body"]
        is_html = arguments.get("is_html", False)

        # If images provided but body is plain text, wrap in simple HTML
        if email_images and not is_html:
            import html as html_mod
            escaped_body = html_mod.escape(email_body).replace("\n", "<br>")
            img_tags = "".join(
                f'<div style="margin-top: 16px;"><img src="cid:notif_img_{i}" style="max-width: 100%;" /></div>'
                for i in range(len(email_images))
            )
            email_body = f'<div style="font-family: sans-serif;">{escaped_body}{img_tags}</div>'
            is_html = True

        return _send_smtp(
            smtp_host=account["smtp_host"],
            smtp_port=account["smtp_port"],
            username=account["username"],
            password=password,
            use_tls=account.get("use_tls", True),
            from_email=account["from_email"],
            from_name=account.get("from_name", ""),
            to=arguments["to"],
            subject=arguments["subject"],
            body=email_body,
            is_html=is_html,
            images=email_images,
        )

    # ── Read tools ──
    imap_host = account.get("imap_host")
    imap_port = account.get("imap_port", 993)
    if not imap_host:
        return {
            "success": False,
            "error": "No IMAP server configured. Set up IMAP settings in the Tools panel to read emails.",
        }

    if tool_name == "read_inbox":
        return _read_inbox(
            imap_host=imap_host,
            imap_port=imap_port,
            username=account["username"],
            password=password,
            count=arguments.get("count", 10),
            unread_only=arguments.get("unread_only", False),
        )
    elif tool_name == "read_email":
        return _read_email_by_id(
            imap_host=imap_host,
            imap_port=imap_port,
            username=account["username"],
            password=password,
            email_id=arguments["email_id"],
        )
    elif tool_name == "search_emails":
        return _search_emails(
            imap_host=imap_host,
            imap_port=imap_port,
            username=account["username"],
            password=password,
            from_address=arguments.get("from_address", ""),
            subject=arguments.get("subject", ""),
            count=arguments.get("count", 10),
        )
    elif tool_name == "read_trigger_email":
        return _read_email_by_uid(
            imap_host=imap_host,
            imap_port=imap_port,
            username=account["username"],
            password=password,
            uid=arguments["uid"],
        )
    else:
        return {"success": False, "error": f"Unknown email tool: {tool_name}"}
