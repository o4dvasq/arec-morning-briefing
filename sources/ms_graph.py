"""
Fetches calendar events and emails from Microsoft Graph API.
"""

import os
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from auth.graph_auth import get_access_token

LOCAL_TZ = ZoneInfo("America/Los_Angeles")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

def _parse_dt(s: str) -> datetime:
    """Parse Microsoft Graph datetime strings, handling 7-decimal microseconds."""
    # Trim to 6 decimal places if longer
    s = s.rstrip("Z")
    if '.' in s:
        base, frac = s.split('.')
        frac = frac[:6]
        s = f"{base}.{frac}"
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)

def _headers():
    return {"Authorization": f"Bearer {get_access_token()}"}

def _get(url, params=None):
    r = requests.get(url, headers=_headers(), params=params)
    r.raise_for_status()
    return r.json()

def get_todays_events(days_ahead: int = 1) -> list[dict]:
    """Fetch calendar events for today."""
    user_id = os.environ["MS_USER_ID"]
    now = datetime.now(LOCAL_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days_ahead)

    data = _get(f"{GRAPH_BASE}/users/{user_id}/calendarView", params={
        "startDateTime": start.isoformat(),
        "endDateTime": end.isoformat(),
        "$select": "subject,start,end,location,organizer,attendees,bodyPreview,isAllDay",
        "$orderby": "start/dateTime",
        "$top": 25,
    })

    events = []
    for e in data.get("value", []):
        start_dt = _parse_dt(e["start"]["dateTime"])
        end_dt = _parse_dt(e["end"]["dateTime"])

        attendees = [
            a["emailAddress"].get("name", a["emailAddress"].get("address", ""))
            for a in e.get("attendees", [])
            if a.get("emailAddress")
        ]

        events.append({
            "title": e.get("subject", "Untitled"),
            "start": start_dt.strftime("%-I:%M %p"),
            "end": end_dt.strftime("%-I:%M %p"),
            "start_sort": start_dt,
            "location": e.get("location", {}).get("displayName", ""),
            "organizer": e.get("organizer", {}).get("emailAddress", {}).get("name", ""),
            "attendees": attendees[:8],
            "preview": e.get("bodyPreview", "")[:200],
            "is_all_day": e.get("isAllDay", False),
        })

    return sorted(events, key=lambda x: x["start_sort"])

def get_recent_emails(hours_back: int = 18, max_results: int = 15) -> list[dict]:
    """Fetch recent inbox emails."""
    user_id = os.environ["MS_USER_ID"]
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    data = _get(
        f"{GRAPH_BASE}/users/{user_id}/mailFolders/Inbox/messages",
        params={
            "$select": "subject,from,receivedDateTime,bodyPreview,hasAttachments,isRead",
            "$orderby": "receivedDateTime desc",
            "$top": max_results,
            "$filter": f"receivedDateTime ge {since} and isDraft eq false",
        }
    )

    emails = []
    for m in data.get("value", []):
        received = _parse_dt(m["receivedDateTime"])

        emails.append({
            "subject": m.get("subject", "(no subject)"),
            "from": m.get("from", {}).get("emailAddress", {}).get("name", "Unknown"),
            "from_email": m.get("from", {}).get("emailAddress", {}).get("address", ""),
            "received": received.strftime("%-I:%M %p"),
            "preview": m.get("bodyPreview", "")[:300],
            "has_attachments": m.get("hasAttachments", False),
            "is_read": m.get("isRead", True),
        })

    return emails
