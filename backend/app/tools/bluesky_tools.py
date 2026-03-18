"""
Bluesky social tools — read and interact with Bluesky via the AT Protocol.

Uses the atproto Python SDK for all operations. Requires a Bluesky
handle (e.g. user.bsky.social) and an App Password configured in
user preferences.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

BLUESKY_TOOL_DEFINITIONS = [
    {
        "name": "bluesky_get_timeline",
        "description": (
            "Fetch the authenticated user's home timeline on Bluesky. "
            "Returns recent posts from accounts the user follows."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of posts to return (max 50, default 20).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "bluesky_get_profile",
        "description": (
            "Get a Bluesky user's profile information including display name, "
            "bio, follower/following counts, and post count."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Bluesky handle (e.g. 'alice.bsky.social'). If omitted, returns the authenticated user's profile.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "bluesky_get_author_feed",
        "description": (
            "Fetch recent posts by a specific Bluesky user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "handle": {
                    "type": "string",
                    "description": "Bluesky handle of the author (e.g. 'alice.bsky.social').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of posts to return (max 50, default 20).",
                },
            },
            "required": ["handle"],
        },
    },
    {
        "name": "bluesky_search_posts",
        "description": (
            "Search for posts on Bluesky matching a query string."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query text.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of results to return (max 50, default 20).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "bluesky_create_post",
        "description": (
            "Create a new post (skeet) on Bluesky. Supports plain text up to 300 characters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The post text (max 300 characters).",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "bluesky_reply",
        "description": (
            "Reply to an existing Bluesky post."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "post_uri": {
                    "type": "string",
                    "description": "The AT URI of the post to reply to (e.g. 'at://did:plc:.../app.bsky.feed.post/...').",
                },
                "post_cid": {
                    "type": "string",
                    "description": "The CID of the post to reply to.",
                },
                "text": {
                    "type": "string",
                    "description": "The reply text (max 300 characters).",
                },
            },
            "required": ["post_uri", "post_cid", "text"],
        },
    },
    {
        "name": "bluesky_repost",
        "description": "Repost (retweet) an existing Bluesky post.",
        "parameters": {
            "type": "object",
            "properties": {
                "post_uri": {
                    "type": "string",
                    "description": "The AT URI of the post to repost.",
                },
                "post_cid": {
                    "type": "string",
                    "description": "The CID of the post to repost.",
                },
            },
            "required": ["post_uri", "post_cid"],
        },
    },
    {
        "name": "bluesky_like",
        "description": "Like a Bluesky post.",
        "parameters": {
            "type": "object",
            "properties": {
                "post_uri": {
                    "type": "string",
                    "description": "The AT URI of the post to like.",
                },
                "post_cid": {
                    "type": "string",
                    "description": "The CID of the post to like.",
                },
            },
            "required": ["post_uri", "post_cid"],
        },
    },
    {
        "name": "bluesky_get_notifications",
        "description": (
            "Fetch the authenticated user's recent notifications (likes, reposts, "
            "follows, replies, mentions)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of notifications to return (max 50, default 20).",
                },
            },
            "required": [],
        },
    },
]

BLUESKY_TOOL_NAMES = {d["name"] for d in BLUESKY_TOOL_DEFINITIONS}


def _get_client():
    """Build an authenticated atproto Client from user preferences."""
    from app.services.user_service import user_service
    from app.tools.email_encryption import decrypt

    prefs = user_service.get_user("1")
    bsky_config = (prefs or {}).get("bluesky_config")
    if not bsky_config:
        raise ValueError(
            "Bluesky is not configured. Add your Bluesky handle and App Password in Settings."
        )

    handle = bsky_config.get("handle", "")
    app_password_enc = bsky_config.get("app_password", "")
    if not handle or not app_password_enc:
        raise ValueError("Bluesky handle and App Password are required.")

    app_password = decrypt(app_password_enc)

    from atproto import Client  # type: ignore[import-untyped]

    client = Client()
    client.login(handle, app_password)
    return client


def execute_bluesky_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    try:
        if tool_name == "bluesky_get_timeline":
            return _get_timeline(arguments)
        elif tool_name == "bluesky_get_profile":
            return _get_profile(arguments)
        elif tool_name == "bluesky_get_author_feed":
            return _get_author_feed(arguments)
        elif tool_name == "bluesky_search_posts":
            return _search_posts(arguments)
        elif tool_name == "bluesky_create_post":
            return _create_post(arguments)
        elif tool_name == "bluesky_reply":
            return _reply(arguments)
        elif tool_name == "bluesky_repost":
            return _repost(arguments)
        elif tool_name == "bluesky_like":
            return _like(arguments)
        elif tool_name == "bluesky_get_notifications":
            return _get_notifications(arguments)
        else:
            return {"success": False, "error": f"Unknown Bluesky tool: {tool_name}"}
    except Exception as e:
        logger.error("Bluesky tool %s failed: %s", tool_name, e, exc_info=True)
        return {"success": False, "error": str(e)}


# ── Helpers ──────────────────────────────────────────────────────

def _format_post(post_view) -> dict:
    """Normalize a post view into a simple dict."""
    post = post_view.post if hasattr(post_view, "post") else post_view
    record = post.record
    author = post.author
    return {
        "uri": post.uri,
        "cid": post.cid,
        "author_handle": author.handle,
        "author_name": getattr(author, "display_name", None) or author.handle,
        "text": getattr(record, "text", ""),
        "created_at": getattr(record, "created_at", None),
        "like_count": getattr(post, "like_count", 0),
        "repost_count": getattr(post, "repost_count", 0),
        "reply_count": getattr(post, "reply_count", 0),
    }


# ── Read operations ─────────────────────────────────────────────

def _get_timeline(args: dict) -> dict:
    client = _get_client()
    limit = min(args.get("limit", 20), 50)
    resp = client.get_timeline(limit=limit)
    posts = [_format_post(item) for item in resp.feed]
    return {"success": True, "posts": posts, "count": len(posts)}


def _get_profile(args: dict) -> dict:
    client = _get_client()
    handle = args.get("handle") or client.me.handle
    profile = client.get_profile(handle)
    return {
        "success": True,
        "profile": {
            "handle": profile.handle,
            "display_name": getattr(profile, "display_name", None),
            "description": getattr(profile, "description", None),
            "followers_count": getattr(profile, "followers_count", 0),
            "follows_count": getattr(profile, "follows_count", 0),
            "posts_count": getattr(profile, "posts_count", 0),
            "avatar": getattr(profile, "avatar", None),
        },
    }


def _get_author_feed(args: dict) -> dict:
    client = _get_client()
    handle = args["handle"]
    limit = min(args.get("limit", 20), 50)
    resp = client.get_author_feed(handle, limit=limit)
    posts = [_format_post(item) for item in resp.feed]
    return {"success": True, "posts": posts, "count": len(posts)}


def _search_posts(args: dict) -> dict:
    client = _get_client()
    query = args["query"]
    limit = min(args.get("limit", 20), 50)
    resp = client.app.bsky.feed.search_posts({"q": query, "limit": limit})
    posts = [_format_post(p) for p in resp.posts]
    return {"success": True, "posts": posts, "count": len(posts)}


# ── Write operations ────────────────────────────────────────────

def _create_post(args: dict) -> dict:
    client = _get_client()
    text = args["text"]
    if len(text) > 300:
        return {"success": False, "error": "Post text exceeds 300 character limit."}
    resp = client.send_post(text=text)
    return {"success": True, "uri": resp.uri, "cid": resp.cid}


def _reply(args: dict) -> dict:
    from atproto import models  # type: ignore[import-untyped]

    client = _get_client()
    text = args["text"]
    if len(text) > 300:
        return {"success": False, "error": "Reply text exceeds 300 character limit."}

    parent_ref = models.create_strong_ref(args["post_uri"], args["post_cid"])
    resp = client.send_post(
        text=text,
        reply_to=models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=parent_ref),
    )
    return {"success": True, "uri": resp.uri, "cid": resp.cid}


def _repost(args: dict) -> dict:
    client = _get_client()
    resp = client.repost(uri=args["post_uri"], cid=args["post_cid"])
    return {"success": True, "uri": resp.uri}


def _like(args: dict) -> dict:
    client = _get_client()
    resp = client.like(uri=args["post_uri"], cid=args["post_cid"])
    return {"success": True, "uri": resp.uri}


# ── Notifications ───────────────────────────────────────────────

def _get_notifications(args: dict) -> dict:
    client = _get_client()
    limit = min(args.get("limit", 20), 50)
    resp = client.app.bsky.notification.list_notifications({"limit": limit})
    notifs = []
    for n in resp.notifications:
        notifs.append({
            "reason": n.reason,
            "author_handle": n.author.handle,
            "author_name": getattr(n.author, "display_name", None) or n.author.handle,
            "is_read": n.is_read,
            "indexed_at": n.indexed_at,
            "uri": n.uri,
        })
    return {"success": True, "notifications": notifs, "count": len(notifs)}
