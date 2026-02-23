"""
Assembles all data sources into a structured prompt for Claude.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")

SYSTEM_PROMPT = """You are Oscar Vasquez's personal morning briefing assistant.
Oscar is the COO and Co-founder of Avila Real Estate Capital (AREC), a private credit
real estate fund focused on residential A&D and construction lending. Hard close for
Fund II is June 30, 2026 with a $1B AUM target.

Deliver a concise, intelligent morning briefing optimized for mobile Slack reading —
exactly like a trusted chief of staff would give. You have access to: today's calendar,
recent emails, Oscar's open task list, and institutional memory about Fund II, investors,
and relationships.

CRITICAL FORMATTING RULES FOR MOBILE:
- Use short, punchy paragraphs (2-3 sentences max each)
- Put a blank line between EVERY paragraph
- Use *bold* for names and times (Slack markdown)
- Start each major section with a bold label on its own line:
  *Schedule*
  *Email — Action Required*
  *Open Tasks*
  *Headline*
- Each action item gets its own short paragraph — NEVER combine two action items
- If a paragraph exceeds 3 sentences, split it immediately
- No walls of text — every sentence should feel scannable on mobile
- No emojis anywhere in the briefing

CONTENT RULES:
- Warm but efficient. No fluff. No filler phrases.
- For meetings: call out who the key people are and why the meeting matters
- For emails: surface only what needs attention or action. Skip automated/noise emails.
- For tasks: flag only what's time-sensitive or relevant to today's meetings
- End with *Headline* section: one bold sentence about the single most important thing today
- Target length: under 400 words total
- Write directly to Oscar in second person.
- Do NOT use markdown headers (#, ##). Only use the bold section markers above.

CRITICAL — NO INFERENCE OR HALLUCINATION:
- Only connect a meeting or person to a topic/deal if there is explicit evidence in the
  email, calendar invite, or memory files that they are related.
- Do NOT infer that a meeting is a good opportunity to discuss something just because
  the timing is convenient.
- A weekly check-in is just a weekly check-in — do not load it with agenda suggestions
  unless the calendar invite or recent emails explicitly reference those topics.
- If confidence in a connection is below 90%, omit it entirely. It is better to
  under-connect than to hallucinate relevance.
- Describe meetings factually: who, what time, what the meeting is for based only on
  what the invite says. Do not editorialize about what Oscar should discuss unless
  the source data explicitly supports it.
- Save recommendations and suggested actions strictly for the Email and Tasks sections
  where there is direct evidence of something requiring attention."""

def _fmt_events(events):
    if not events:
        return "No calendar events today."
    lines = []
    for e in events:
        if e["is_all_day"]:
            lines.append(f"- ALL DAY: {e['title']}")
            continue
        att = ""
        if e["attendees"]:
            names = e["attendees"][:4]
            att = f" with {', '.join(names)}"
            if len(e["attendees"]) > 4:
                att += f" +{len(e['attendees'])-4} others"
        loc = f" @ {e['location']}" if e["location"] else ""
        lines.append(f"- {e['start']} – {e['end']}: {e['title']}{att}{loc}")
        if e.get("preview", "").strip():
            lines.append(f"  {e['preview'][:150]}")
    return "\n".join(lines)

def _fmt_emails(emails):
    if not emails:
        return "No recent emails."
    lines = []
    for m in emails:
        unread = "" if m["is_read"] else "[UNREAD] "
        att = " [attachment]" if m["has_attachments"] else ""
        lines.append(f"- {unread}FROM: {m['from']} | {m['subject']}{att}")
        if m.get("preview"):
            lines.append(f"  {m['preview'][:200]}")
    return "\n".join(lines)

def _fmt_tasks(open_tasks):
    if not open_tasks:
        return "No open tasks."
    lines = []
    for cat, tasks in open_tasks.items():
        if tasks:
            lines.append(f"\n{cat}:")
            for t in tasks:
                lines.append(f"  - {t}")
    return "\n".join(lines)

def _fmt_people(people, events):
    """Only surface people context for names appearing in today's events."""
    if not events or not people:
        return ""
    attendees_flat = " ".join(
        a.lower() for e in events for a in e.get("attendees", [])
    )
    relevant = {
        name: bio for name, bio in people.items()
        if any(part.lower() in attendees_flat for part in name.split())
    }
    if not relevant:
        return ""
    lines = ["Relevant people in today's meetings:"]
    for name, bio in relevant.items():
        lines.append(f"\n{name}:\n{bio[:300]}")
    return "\n".join(lines)

def build_prompt(events, emails, memory, config) -> tuple[str, str]:
    today = datetime.now(LOCAL_TZ).strftime("%A, %B %-d, %Y")
    time_now = datetime.now(LOCAL_TZ).strftime("%-I:%M %p")

    user_prompt = f"""Today is {today}. Current time: {time_now} Pacific.

=== TODAY'S CALENDAR ===
{_fmt_events(events)}

=== RECENT EMAILS (past 18 hours) ===
{_fmt_emails(emails)}

=== OPEN TASKS ===
{_fmt_tasks(memory['open_tasks'])}

=== INBOX CAPTURE QUEUE ===
{chr(10).join(memory['inbox_items']) if memory['inbox_items'] else 'Empty.'}

=== FUND II STATUS ===
{memory['fund_ii']}

=== COMPANY CONTEXT ===
{memory['company'][:800]}

=== PEOPLE CONTEXT ===
{_fmt_people(memory['people'], events)}

Please deliver Oscar's morning briefing for today."""

    return SYSTEM_PROMPT, user_prompt
