"""
Function tool definitions for the cross-agent notification / alert system.

Agents call `send_notification` to push an alert to the user.
The notification always appears in-app (bell icon).  Additionally it is
delivered to every *enabled* notification channel the user has configured
(e.g. email addresses).
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
            "in the user's notification bell and is also delivered to all "
            "configured notification channels (e.g. email). "
            "Use this to inform the user about important events — price alerts, "
            "completed tasks, trigger results, reports, errors, or anything "
            "worth flagging. "
            "The 'content' field should contain a detailed report or full "
            "analysis that will be included in the email; 'body' is a short "
            "summary shown in the bell."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "Short notification title, e.g. 'BTC Price Alert', "
                        "'Task Complete', 'Daily Report'"
                    ),
                },
                "body": {
                    "type": "string",
                    "description": (
                        "Short summary shown in the notification bell "
                        "(1-2 sentences)."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Detailed report or full analysis to include in email "
                        "delivery. Can be multiple paragraphs. If omitted, "
                        "the body is used instead."
                    ),
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
                "image_base64": {
                    "type": "string",
                    "description": (
                        "Base64-encoded image data to include with the notification. "
                        "Used when you want to attach a captured image (e.g. from "
                        "a Twitch stream capture) to the notification and email."
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
    thread_id: str | None = None,
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
    content = arguments.get("content", "")
    level = arguments.get("level", "info")
    image_base64 = arguments.get("image_base64", "")
    image_media_type = arguments.get("image_media_type", "image/jpeg")

    # If no explicit image param, try the thread image cache
    if not image_base64 and thread_id:
        from app.services.agent_service import _thread_images, _thread_images_lock
        with _thread_images_lock:
            cached = _thread_images.get(thread_id, [])
            if cached:
                image_base64 = cached[-1]["data"]
                image_media_type = cached[-1].get("media_type", "image/jpeg")

    # Build images list for storage/delivery
    images: list[dict] | None = None
    if image_base64:
        images = [{"data": image_base64, "media_type": image_media_type}]

    if not title or not body:
        return {"success": False, "error": "title and body are required"}

    try:
        from app.services.notification_service import notification_service
        from app.services.user_service import user_service

        # Always create in-app notification
        doc = notification_service.create_notification(
            title=title,
            body=body,
            content=content,
            level=level,
            agent_id=agent_id,
            agent_name=agent_name,
            user_id=user_id,
            images=images,
        )

        # Deliver to all enabled channels
        channels = user_service.get_enabled_notification_channels(user_id)
        channels_sent = 0
        for ch in channels:
            if ch["type"] == "email":
                ok = _send_to_email_channel(
                    to_email=ch["address"],
                    title=title,
                    body=body,
                    content=content,
                    level=level,
                    agent_name=agent_name,
                    images=images,
                )
                if ok:
                    channels_sent += 1

        return {
            "success": True,
            "delivered": True,
            "notification_id": doc["id"],
            "channels_notified": channels_sent,
        }

    except Exception as e:
        logger.error("Failed to send notification: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


def _send_to_email_channel(
    *,
    to_email: str,
    title: str,
    body: str,
    content: str = "",
    level: str = "info",
    agent_name: str | None = None,
    user_id: str = "1",
    images: list[dict] | None = None,
) -> bool:
    """Send a notification email to a specific email channel address."""
    try:
        from app.services.user_service import user_service
        from app.tools.email_encryption import decrypt

        account = user_service.get_email_account(user_id)
        if not account:
            logger.debug("No email account configured — cannot send to channel")
            return False

        password = decrypt(account["password_encrypted"])
        from_email = account["from_email"]
        from_name = account.get("from_name", "Cronosaurus")

        level_emoji = {
            "info": "ℹ️", "success": "✅",
            "warning": "⚠️", "error": "❌",
        }.get(level, "🔔")

        subject = f"{level_emoji} {title}"
        if agent_name:
            subject += f" — {agent_name}"

        # Use content for the detailed section, fall back to body
        detail_text = content or body

        # Build image HTML section (inline CID references)
        image_html = ""
        if images:
            for i, _img in enumerate(images):
                image_html += (
                    f'<div style="margin-top: 16px;">'
                    f'<img src="cid:notif_img_{i}" style="max-width: 100%; border-radius: 8px; border: 1px solid #333;" />'
                    f'</div>'
                )

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #1a1a2e; border-radius: 12px; padding: 24px; color: #e0e0e0;">
                <div style="font-size: 14px; color: #888; margin-bottom: 8px;">
                    🦖 Cronosaurus Notification{f' — {agent_name}' if agent_name else ''}
                </div>
                <h2 style="margin: 0 0 12px 0; color: #fff; font-size: 18px;">
                    {level_emoji} {title}
                </h2>
                <p style="margin: 0 0 16px 0; line-height: 1.5; color: #aaa; font-size: 14px;">
                    {body}
                </p>
                <div style="border-top: 1px solid #333; padding-top: 16px; line-height: 1.7; color: #ccc; white-space: pre-wrap; font-size: 14px;">
                    {detail_text}
                </div>
                {image_html}
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
            images=images,
        )
        return result.get("success", False)

    except Exception as e:
        logger.warning("Failed to send notification to %s: %s", to_email, e)
        return False
