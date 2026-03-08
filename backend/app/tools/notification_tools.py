"""
Function tool definitions for the cross-agent notification / alert system.

Agents call `send_notification` to push an alert to the user.
Delivery (in-app bell, email, or both) is controlled by user preferences.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── JSON-Schema definition (OpenAI function-calling format) ─────

NOTIFICATION_TOOL_DEFINITIONS = [
    {
        "name": "send_notification",
        "description": (
            "Send a notification/alert to the user. The notification appears "
            "in the user's notification bell and may also be emailed, depending "
            "on the user's notification preferences. Use this to inform the user "
            "about important events — price alerts, completed tasks, trigger "
            "results, errors, or anything worth flagging."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "Short notification title, e.g. 'BTC Price Alert', "
                        "'Email Sent', 'Task Complete'"
                    ),
                },
                "body": {
                    "type": "string",
                    "description": "Detailed notification message body.",
                },
                "level": {
                    "type": "string",
                    "enum": ["info", "success", "warning", "error"],
                    "description": (
                        "Severity: info (general), success (task completed), "
                        "warning (attention needed), error (something failed). "
                        "Defaults to info."
                    ),
                },
            },
            "required": ["title", "body"],
        },
    },
]

NOTIFICATION_TOOL_NAMES = {d["name"] for d in NOTIFICATION_TOOL_DEFINITIONS}


def execute_notification_tool(
    tool_name: str,
    arguments: str | dict,
    agent_id: str | None = None,
    agent_name: str | None = None,
    user_id: str = "1",
) -> dict[str, Any]:
    """Execute a notification tool call."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    if tool_name != "send_notification":
        return {"success": False, "error": f"Unknown notification tool: {tool_name}"}

    title = arguments.get("title", "")
    body = arguments.get("body", "")
    level = arguments.get("level", "info")

    if not title or not body:
        return {"success": False, "error": "title and body are required"}

    try:
        from app.services.notification_service import notification_service
        from app.services.user_service import user_service

        # Check user preferences
        prefs = user_service.get_notification_preferences(user_id)
        delivery = prefs.get("delivery", "all")

        if delivery == "none":
            return {
                "success": True,
                "delivered": False,
                "reason": "User has muted all notifications.",
            }

        # Always create in-app notification (unless muted)
        doc = notification_service.create_notification(
            title=title,
            body=body,
            level=level,
            agent_id=agent_id,
            agent_name=agent_name,
            user_id=user_id,
        )

        email_sent = False

        # Also send email if user chose "all"
        if delivery == "all":
            email_sent = _send_notification_email(
                title=title,
                body=body,
                level=level,
                agent_name=agent_name,
                user_id=user_id,
            )

        return {
            "success": True,
            "delivered": True,
            "notification_id": doc["id"],
            "email_sent": email_sent,
        }

    except Exception as e:
        logger.error("Failed to send notification: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


def _send_notification_email(
    title: str,
    body: str,
    level: str,
    agent_name: str | None,
    user_id: str,
) -> bool:
    """Try to send the notification via the user's configured email account."""
    try:
        from app.services.user_service import user_service
        from app.tools.email_encryption import decrypt

        account = user_service.get_email_account(user_id)
        if not account:
            logger.debug("No email account configured — skipping email notification")
            return False

        password = decrypt(account["password_encrypted"])
        from_email = account["from_email"]
        from_name = account.get("from_name", "Cronosaurus")
        to_email = from_email  # Send to self

        level_emoji = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(level, "🔔")
        subject = f"{level_emoji} {title}"
        if agent_name:
            subject += f" — {agent_name}"

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 20px;">
            <div style="background: #1a1a2e; border-radius: 12px; padding: 24px; color: #e0e0e0;">
                <div style="font-size: 14px; color: #888; margin-bottom: 8px;">
                    🦖 Cronosaurus Notification{f' — {agent_name}' if agent_name else ''}
                </div>
                <h2 style="margin: 0 0 12px 0; color: #fff; font-size: 18px;">
                    {level_emoji} {title}
                </h2>
                <p style="margin: 0; line-height: 1.6; color: #ccc; white-space: pre-wrap;">
                    {body}
                </p>
            </div>
        </div>
        """

        from app.tools.email_tools import _send_smtp
        result = _send_smtp(
            smtp_host=account["smtp_host"],
            smtp_port=account["smtp_port"],
            username=account["username"],
            password=password,
            use_tls=account.get("use_tls", True),
            from_email=from_email,
            from_name=from_name,
            to=to_email,
            subject=subject,
            body=html_body,
            is_html=True,
        )
        return result.get("success", False)

    except Exception as e:
        logger.warning("Failed to send notification email: %s", e)
        return False
