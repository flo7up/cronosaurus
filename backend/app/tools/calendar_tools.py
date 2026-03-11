"""
Calendar tools — read and manage calendar events via CalDAV.

Supports:
  - Google Calendar (CalDAV via app password)
  - Apple iCloud Calendar (CalDAV via app-specific password)
  - Nextcloud / any CalDAV server
  - Read-only ICS URL feeds (any provider)

Configuration is stored per-user in user_service (calendar_accounts).
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── JSON-Schema definitions ─────────────────────────────────────

CALENDAR_TOOL_DEFINITIONS = [
    {
        "name": "list_calendars",
        "description": (
            "List all available calendars for the user's configured calendar account. "
            "Returns calendar names and IDs. Use this to discover which calendars "
            "are available before reading or creating events."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_calendar_events",
        "description": (
            "Get calendar events within a date range. Returns event titles, times, "
            "locations, descriptions, and attendees. Defaults to the next 7 days "
            "if no dates specified."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": (
                        "Start of the date range in ISO 8601 format (e.g. '2026-03-11'). "
                        "Defaults to today."
                    ),
                },
                "end_date": {
                    "type": "string",
                    "description": (
                        "End of the date range in ISO 8601 format (e.g. '2026-03-18'). "
                        "Defaults to 7 days from start."
                    ),
                },
                "calendar_name": {
                    "type": "string",
                    "description": (
                        "Name of the calendar to read. If omitted, reads from "
                        "the default/primary calendar."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_calendar_event",
        "description": (
            "Create a new event on the user's calendar. Specify title, start/end times, "
            "and optional location, description, and attendees."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title/summary.",
                },
                "start": {
                    "type": "string",
                    "description": (
                        "Event start time in ISO 8601 format "
                        "(e.g. '2026-03-12T14:00:00'). Include timezone if needed."
                    ),
                },
                "end": {
                    "type": "string",
                    "description": (
                        "Event end time in ISO 8601 format "
                        "(e.g. '2026-03-12T15:00:00'). Defaults to 1 hour after start."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Event description/notes.",
                },
                "location": {
                    "type": "string",
                    "description": "Event location (physical address or URL).",
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses to invite.",
                },
                "calendar_name": {
                    "type": "string",
                    "description": "Which calendar to create the event in. Defaults to primary.",
                },
                "all_day": {
                    "type": "boolean",
                    "description": "If true, create an all-day event. Only start date needed.",
                },
            },
            "required": ["title", "start"],
        },
    },
    {
        "name": "search_calendar_events",
        "description": (
            "Search calendar events by keyword. Searches event titles and descriptions. "
            "Useful for finding specific meetings or appointments."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword to match in event titles and descriptions.",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "How many days ahead to search. Defaults to 30.",
                },
            },
            "required": ["query"],
        },
    },
]

CALENDAR_TOOL_NAMES = {d["name"] for d in CALENDAR_TOOL_DEFINITIONS}


# ── CalDAV provider configurations ──────────────────────────────

CALDAV_PROVIDERS = {
    "google": {
        "label": "Google Calendar",
        "url": "https://www.googleapis.com/caldav/v2/{username}/user",
        "notes": "Use an app-specific password from https://myaccount.google.com/apppasswords",
    },
    "icloud": {
        "label": "Apple iCloud",
        "url": "https://caldav.icloud.com/",
        "notes": "Use an app-specific password from https://appleid.apple.com",
    },
    "nextcloud": {
        "label": "Nextcloud",
        "url": "{url}/remote.php/dav/",
        "notes": "Use your Nextcloud URL and credentials",
    },
    "custom": {
        "label": "Custom CalDAV",
        "url": "",
        "notes": "Any CalDAV-compatible server",
    },
}


# ── Tool execution ──────────────────────────────────────────────

def execute_calendar_tool(
    tool_name: str,
    arguments: str | dict,
    user_id: str = "1",
) -> dict[str, Any]:
    """Execute a calendar tool call."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid arguments JSON"}

    # Get calendar config from user service
    try:
        from app.services.user_service import user_service
        config = user_service.get_calendar_config(user_id)
        if not config or not config.get("caldav_url"):
            return {
                "success": False,
                "error": (
                    "Calendar not configured. Please set up a calendar account "
                    "in Settings > Connections with your CalDAV URL and credentials."
                ),
            }
    except Exception as e:
        return {"success": False, "error": f"Failed to load calendar config: {e}"}

    try:
        if tool_name == "list_calendars":
            return _list_calendars(config)
        elif tool_name == "get_calendar_events":
            return _get_events(config, arguments)
        elif tool_name == "create_calendar_event":
            return _create_event(config, arguments)
        elif tool_name == "search_calendar_events":
            return _search_events(config, arguments)
        else:
            return {"success": False, "error": f"Unknown calendar tool: {tool_name}"}
    except Exception as e:
        logger.error("Calendar tool %s failed: %s", tool_name, e, exc_info=True)
        return {"success": False, "error": str(e)}


def _get_caldav_client(config: dict):
    """Create a CalDAV client from user config."""
    try:
        import caldav
    except ImportError:
        raise RuntimeError(
            "caldav package not installed. Run: pip install caldav"
        )

    url = config["caldav_url"]
    username = config.get("username", "")
    password = config.get("password", "")

    client = caldav.DAVClient(
        url=url,
        username=username,
        password=password,
    )
    return client


def _get_calendar(config: dict, calendar_name: str | None = None):
    """Get a specific calendar or the default/first one."""
    client = _get_caldav_client(config)
    principal = client.principal()
    calendars = principal.calendars()

    if not calendars:
        raise RuntimeError("No calendars found on this account")

    if calendar_name:
        for cal in calendars:
            if cal.name and cal.name.lower() == calendar_name.lower():
                return cal
        raise RuntimeError(f"Calendar '{calendar_name}' not found")

    # Return the first calendar (usually the primary)
    return calendars[0]


def _list_calendars(config: dict) -> dict:
    """List all available calendars."""
    client = _get_caldav_client(config)
    principal = client.principal()
    calendars = principal.calendars()

    result = []
    for cal in calendars:
        result.append({
            "name": cal.name or "(unnamed)",
            "id": str(cal.url),
        })

    return {
        "success": True,
        "calendars": result,
        "count": len(result),
    }


def _parse_event(event) -> dict:
    """Parse a CalDAV event into a clean dict."""
    try:
        import icalendar
    except ImportError:
        raise RuntimeError("icalendar package not installed. Run: pip install icalendar")

    cal = icalendar.Calendar.from_ical(event.data)
    for component in cal.walk():
        if component.name == "VEVENT":
            dtstart = component.get("dtstart")
            dtend = component.get("dtend")
            summary = str(component.get("summary", ""))
            description = str(component.get("description", ""))
            location = str(component.get("location", ""))

            start_str = ""
            end_str = ""
            all_day = False

            if dtstart:
                dt = dtstart.dt
                if hasattr(dt, "hour"):
                    start_str = dt.isoformat()
                else:
                    start_str = dt.isoformat()
                    all_day = True

            if dtend:
                dt = dtend.dt
                end_str = dt.isoformat()

            attendees = []
            att = component.get("attendee")
            if att:
                if isinstance(att, list):
                    attendees = [str(a).replace("mailto:", "") for a in att]
                else:
                    attendees = [str(att).replace("mailto:", "")]

            result = {
                "title": summary,
                "start": start_str,
                "end": end_str,
                "all_day": all_day,
            }
            if description:
                result["description"] = description
            if location:
                result["location"] = location
            if attendees:
                result["attendees"] = attendees
            return result

    return {"title": "(could not parse event)"}


def _get_events(config: dict, args: dict) -> dict:
    """Get events in a date range."""
    now = datetime.now(timezone.utc)

    start_str = args.get("start_date", "")
    end_str = args.get("end_date", "")
    calendar_name = args.get("calendar_name")

    if start_str:
        start = datetime.fromisoformat(start_str)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if end_str:
        end = datetime.fromisoformat(end_str)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    else:
        end = start + timedelta(days=7)

    cal = _get_calendar(config, calendar_name)
    events = cal.date_search(start=start, end=end, expand=True)

    parsed = []
    for ev in events:
        parsed.append(_parse_event(ev))

    # Sort by start time
    parsed.sort(key=lambda e: e.get("start", ""))

    return {
        "success": True,
        "events": parsed,
        "count": len(parsed),
        "date_range": f"{start.date().isoformat()} to {end.date().isoformat()}",
    }


def _create_event(config: dict, args: dict) -> dict:
    """Create a new calendar event."""
    try:
        import icalendar
    except ImportError:
        raise RuntimeError("icalendar package not installed. Run: pip install icalendar")

    title = args.get("title", "")
    start_str = args.get("start", "")
    end_str = args.get("end", "")
    description = args.get("description", "")
    location = args.get("location", "")
    attendees = args.get("attendees", [])
    calendar_name = args.get("calendar_name")
    all_day = args.get("all_day", False)

    if not title or not start_str:
        return {"success": False, "error": "title and start are required"}

    start_dt = datetime.fromisoformat(start_str)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    if end_str:
        end_dt = datetime.fromisoformat(end_str)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
    else:
        if all_day:
            end_dt = start_dt + timedelta(days=1)
        else:
            end_dt = start_dt + timedelta(hours=1)

    # Build iCalendar event
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Cronosaurus//Calendar Tool//EN")
    cal.add("version", "2.0")

    event = icalendar.Event()
    event.add("uid", f"{uuid4()}@cronosaurus")
    event.add("summary", title)
    event.add("dtstamp", datetime.now(timezone.utc))

    if all_day:
        event.add("dtstart", start_dt.date())
        event.add("dtend", end_dt.date())
    else:
        event.add("dtstart", start_dt)
        event.add("dtend", end_dt)

    if description:
        event.add("description", description)
    if location:
        event.add("location", location)
    for attendee_email in attendees:
        event.add("attendee", f"mailto:{attendee_email}")

    cal.add_component(event)

    # Upload to CalDAV
    calendar = _get_calendar(config, calendar_name)
    calendar.save_event(cal.to_ical().decode("utf-8"))

    return {
        "success": True,
        "created": {
            "title": title,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "all_day": all_day,
            "location": location or None,
            "attendees": attendees or None,
        },
    }


def _search_events(config: dict, args: dict) -> dict:
    """Search events by keyword."""
    query = args.get("query", "")
    days_ahead = args.get("days_ahead", 30)

    if not query:
        return {"success": False, "error": "query is required"}

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days_ahead)

    # Get all events in range, then filter
    cal = _get_calendar(config)
    events = cal.date_search(start=start, end=end, expand=True)

    query_lower = query.lower()
    matches = []
    for ev in events:
        parsed = _parse_event(ev)
        title = parsed.get("title", "").lower()
        desc = parsed.get("description", "").lower()
        if query_lower in title or query_lower in desc:
            matches.append(parsed)

    matches.sort(key=lambda e: e.get("start", ""))

    return {
        "success": True,
        "events": matches,
        "count": len(matches),
        "query": query,
        "searched_days": days_ahead,
    }
