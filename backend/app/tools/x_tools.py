"""
X (Twitter) social tools — read and interact with X via the v2 API.

Uses tweepy for all operations. Supports both Free and paid (Basic/Pro)
API tiers. Free-tier actions are available to all users; paid actions
will return a clear error if the user's API key lacks access.

Free tier:  create post, delete own post, read own profile
Basic tier: read timeline, search, like, repost, reply, bookmark,
            read other users' profiles, read followers/following
Pro tier:   full-archive search, higher rate limits

Requires an X API Bearer Token (and OAuth 1.0a keys for write actions)
configured in user preferences.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

X_TOOL_DEFINITIONS = [
    # ── Free-tier actions ────────────────────────────────────────
    {
        "name": "x_create_post",
        "description": (
            "Create a new post (tweet) on X. Supports text up to 280 characters. "
            "[Free tier]"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The post text (max 280 characters).",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "x_delete_post",
        "description": "Delete one of your own posts on X. [Free tier]",
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to delete.",
                },
            },
            "required": ["tweet_id"],
        },
    },
    {
        "name": "x_get_me",
        "description": (
            "Get the authenticated user's own X profile (name, handle, bio, "
            "follower counts, verified status). [Free tier]"
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── Basic-tier actions ───────────────────────────────────────
    {
        "name": "x_get_user",
        "description": (
            "Get an X user's public profile by username. Returns display name, "
            "bio, follower/following counts, verified status. [Basic tier — requires paid API]"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "X username without the @ (e.g. 'elonmusk').",
                },
            },
            "required": ["username"],
        },
    },
    {
        "name": "x_get_user_tweets",
        "description": (
            "Fetch recent tweets from a specific X user. "
            "[Basic tier — requires paid API]"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "X username without the @ (e.g. 'elonmusk').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of tweets to return (5-100, default 10).",
                },
            },
            "required": ["username"],
        },
    },
    {
        "name": "x_search_recent",
        "description": (
            "Search recent tweets (last 7 days) matching a query. Supports "
            "X search operators (from:, to:, has:, is:, etc.). "
            "[Basic tier — requires paid API]"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (supports X search operators).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results (10-100, default 10).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "x_like",
        "description": "Like a tweet on X. [Basic tier — requires paid API]",
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to like.",
                },
            },
            "required": ["tweet_id"],
        },
    },
    {
        "name": "x_unlike",
        "description": "Remove a like from a tweet on X. [Basic tier — requires paid API]",
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to unlike.",
                },
            },
            "required": ["tweet_id"],
        },
    },
    {
        "name": "x_repost",
        "description": "Repost (retweet) a tweet on X. [Basic tier — requires paid API]",
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to repost.",
                },
            },
            "required": ["tweet_id"],
        },
    },
    {
        "name": "x_undo_repost",
        "description": "Undo a repost (unretweet) on X. [Basic tier — requires paid API]",
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to unrepost.",
                },
            },
            "required": ["tweet_id"],
        },
    },
    {
        "name": "x_reply",
        "description": (
            "Reply to an existing tweet on X. "
            "[Basic tier — requires paid API for reading the parent; posting itself is free]"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to reply to.",
                },
                "text": {
                    "type": "string",
                    "description": "The reply text (max 280 characters).",
                },
            },
            "required": ["tweet_id", "text"],
        },
    },
    {
        "name": "x_bookmark",
        "description": "Bookmark a tweet for later. [Basic tier — requires paid API]",
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to bookmark.",
                },
            },
            "required": ["tweet_id"],
        },
    },
    {
        "name": "x_remove_bookmark",
        "description": "Remove a bookmarked tweet. [Basic tier — requires paid API]",
        "parameters": {
            "type": "object",
            "properties": {
                "tweet_id": {
                    "type": "string",
                    "description": "The ID of the tweet to remove from bookmarks.",
                },
            },
            "required": ["tweet_id"],
        },
    },
    {
        "name": "x_get_timeline",
        "description": (
            "Fetch the authenticated user's home timeline (reverse-chronological). "
            "[Basic tier — requires paid API]"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Number of tweets to return (1-100, default 20).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "x_get_mentions",
        "description": (
            "Fetch recent tweets mentioning the authenticated user. "
            "[Basic tier — requires paid API]"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Number of results (5-100, default 10).",
                },
            },
            "required": [],
        },
    },
]

X_TOOL_NAMES = {d["name"] for d in X_TOOL_DEFINITIONS}

# Actions available on the free tier (no paid plan required)
_FREE_TIER_TOOLS = {"x_create_post", "x_delete_post", "x_get_me", "x_reply"}

_TWEET_FIELDS = [
    "id", "text", "author_id", "created_at", "public_metrics",
    "conversation_id", "in_reply_to_user_id", "referenced_tweets",
]
_USER_FIELDS = [
    "id", "name", "username", "description", "public_metrics",
    "profile_image_url", "verified", "created_at",
]


def _get_client():
    """Build authenticated tweepy.Client from user preferences."""
    from app.services.user_service import user_service
    from app.tools.email_encryption import decrypt

    prefs = user_service.get_user("1")
    x_config = (prefs or {}).get("x_config")
    if not x_config:
        raise ValueError(
            "X (Twitter) is not configured. Add your API keys in Settings."
        )

    bearer_token_enc = x_config.get("bearer_token", "")
    api_key = x_config.get("api_key", "")
    api_secret_enc = x_config.get("api_secret", "")
    access_token = x_config.get("access_token", "")
    access_secret_enc = x_config.get("access_token_secret", "")

    if not bearer_token_enc:
        raise ValueError("X Bearer Token is required.")

    bearer_token = decrypt(bearer_token_enc)
    api_secret = decrypt(api_secret_enc) if api_secret_enc else None
    access_secret = decrypt(access_secret_enc) if access_secret_enc else None

    import tweepy  # type: ignore[import-untyped]

    return tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=api_key or None,
        consumer_secret=api_secret,
        access_token=access_token or None,
        access_token_secret=access_secret,
    )


def execute_x_tool(tool_name: str, arguments: str | dict) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    try:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return {"success": False, "error": f"Unknown X tool: {tool_name}"}
        return handler(arguments)
    except Exception as e:
        msg = str(e)
        # Surface clear message for tier-restricted endpoints
        if "403" in msg or "Forbidden" in msg:
            tier_note = (
                " This action requires a paid X API plan (Basic or Pro)."
                if tool_name not in _FREE_TIER_TOOLS
                else ""
            )
            return {
                "success": False,
                "error": f"Access denied by X API.{tier_note} Details: {msg}",
            }
        logger.error("X tool %s failed: %s", tool_name, e, exc_info=True)
        return {"success": False, "error": msg}


# ── Helpers ──────────────────────────────────────────────────────

def _format_tweet(tweet) -> dict:
    """Normalize a tweepy Tweet into a simple dict."""
    metrics = tweet.public_metrics or {}
    return {
        "id": tweet.id,
        "text": tweet.text,
        "author_id": tweet.author_id,
        "created_at": str(tweet.created_at) if tweet.created_at else None,
        "like_count": metrics.get("like_count", 0),
        "repost_count": metrics.get("retweet_count", 0),
        "reply_count": metrics.get("reply_count", 0),
        "quote_count": metrics.get("quote_count", 0),
    }


def _format_user(user) -> dict:
    """Normalize a tweepy User into a simple dict."""
    metrics = user.public_metrics or {}
    return {
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "description": getattr(user, "description", None),
        "followers_count": metrics.get("followers_count", 0),
        "following_count": metrics.get("following_count", 0),
        "tweet_count": metrics.get("tweet_count", 0),
        "verified": getattr(user, "verified", False),
        "profile_image_url": getattr(user, "profile_image_url", None),
    }


# ── Free-tier operations ────────────────────────────────────────

def _create_post(args: dict) -> dict:
    client = _get_client()
    text = args["text"]
    if len(text) > 280:
        return {"success": False, "error": "Post text exceeds 280 character limit."}
    resp = client.create_tweet(text=text)
    return {"success": True, "tweet_id": str(resp.data["id"])}


def _delete_post(args: dict) -> dict:
    client = _get_client()
    client.delete_tweet(args["tweet_id"])
    return {"success": True}


def _get_me(args: dict) -> dict:
    client = _get_client()
    resp = client.get_me(user_fields=_USER_FIELDS)
    return {"success": True, "user": _format_user(resp.data)}


# ── Basic-tier operations ───────────────────────────────────────

def _get_user(args: dict) -> dict:
    client = _get_client()
    resp = client.get_user(username=args["username"], user_fields=_USER_FIELDS)
    if resp.data is None:
        return {"success": False, "error": f"User @{args['username']} not found."}
    return {"success": True, "user": _format_user(resp.data)}


def _get_user_tweets(args: dict) -> dict:
    client = _get_client()
    user_resp = client.get_user(username=args["username"], user_fields=["id"])
    if user_resp.data is None:
        return {"success": False, "error": f"User @{args['username']} not found."}
    max_results = max(5, min(args.get("max_results", 10), 100))
    resp = client.get_users_tweets(
        user_resp.data.id, max_results=max_results, tweet_fields=_TWEET_FIELDS,
    )
    tweets = [_format_tweet(t) for t in (resp.data or [])]
    return {"success": True, "tweets": tweets, "count": len(tweets)}


def _search_recent(args: dict) -> dict:
    client = _get_client()
    max_results = max(10, min(args.get("max_results", 10), 100))
    resp = client.search_recent_tweets(
        query=args["query"], max_results=max_results, tweet_fields=_TWEET_FIELDS,
    )
    tweets = [_format_tweet(t) for t in (resp.data or [])]
    return {"success": True, "tweets": tweets, "count": len(tweets)}


def _like(args: dict) -> dict:
    client = _get_client()
    me = client.get_me()
    client.like(args["tweet_id"], user_auth=True)
    return {"success": True}


def _unlike(args: dict) -> dict:
    client = _get_client()
    client.unlike(args["tweet_id"], user_auth=True)
    return {"success": True}


def _repost(args: dict) -> dict:
    client = _get_client()
    client.retweet(args["tweet_id"], user_auth=True)
    return {"success": True}


def _undo_repost(args: dict) -> dict:
    client = _get_client()
    client.unretweet(args["tweet_id"], user_auth=True)
    return {"success": True}


def _reply(args: dict) -> dict:
    client = _get_client()
    text = args["text"]
    if len(text) > 280:
        return {"success": False, "error": "Reply text exceeds 280 character limit."}
    resp = client.create_tweet(text=text, in_reply_to_tweet_id=args["tweet_id"])
    return {"success": True, "tweet_id": str(resp.data["id"])}


def _bookmark(args: dict) -> dict:
    client = _get_client()
    client.bookmark(args["tweet_id"])
    return {"success": True}


def _remove_bookmark(args: dict) -> dict:
    client = _get_client()
    client.remove_bookmark(args["tweet_id"])
    return {"success": True}


def _get_timeline(args: dict) -> dict:
    client = _get_client()
    max_results = max(1, min(args.get("max_results", 20), 100))
    resp = client.get_home_timeline(
        max_results=max_results, tweet_fields=_TWEET_FIELDS,
    )
    tweets = [_format_tweet(t) for t in (resp.data or [])]
    return {"success": True, "tweets": tweets, "count": len(tweets)}


def _get_mentions(args: dict) -> dict:
    client = _get_client()
    me = client.get_me()
    max_results = max(5, min(args.get("max_results", 10), 100))
    resp = client.get_users_mentions(
        me.data.id, max_results=max_results, tweet_fields=_TWEET_FIELDS,
    )
    tweets = [_format_tweet(t) for t in (resp.data or [])]
    return {"success": True, "tweets": tweets, "count": len(tweets)}


# ── Handler map ──────────────────────────────────────────────────

_HANDLERS: dict[str, Any] = {
    "x_create_post": _create_post,
    "x_delete_post": _delete_post,
    "x_get_me": _get_me,
    "x_get_user": _get_user,
    "x_get_user_tweets": _get_user_tweets,
    "x_search_recent": _search_recent,
    "x_like": _like,
    "x_unlike": _unlike,
    "x_repost": _repost,
    "x_undo_repost": _undo_repost,
    "x_reply": _reply,
    "x_bookmark": _bookmark,
    "x_remove_bookmark": _remove_bookmark,
    "x_get_timeline": _get_timeline,
    "x_get_mentions": _get_mentions,
}
