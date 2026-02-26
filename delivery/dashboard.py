#!/usr/bin/env python3
"""
AREC Dashboard — Flask web app serving a single-page dashboard.
Reads from ~/Dropbox/Tech/ClaudeProductivity/ and displays tasks,
calendar events, meeting summaries, and investor pipeline.
"""

import os
import sys
import re
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify
from dotenv import load_dotenv

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_path = project_root / ".env"
load_dotenv(env_path)

# Import MS Graph functions
from sources.ms_graph import get_todays_events

app = Flask(__name__)

# Data directory
DATA_DIR = Path.home() / "Dropbox" / "Tech" / "ClaudeProductivity"
MEETING_SUMMARIES_DIR = DATA_DIR / "meeting-summaries"
MEETING_ARCHIVE_DIR = MEETING_SUMMARIES_DIR / "archive"

# === DATA PARSING FUNCTIONS ===

def shorten_section(name: str) -> str:
    """Shorten section names for display."""
    mapping = {
        'Work — IR/Fundraising': 'IR / FUNDRAISING',
        'Work — Operations': 'OPERATIONS',
        'Work — Finance': 'FINANCE',
        'Work — IT/Systems': 'IT / SYSTEMS',
        'Personal — Home': 'HOME',
        'Personal — Arboleda (Colombia property)': 'ARBOLEDA',
        'Personal — Finance': 'PERSONAL FINANCE',
        'Personal — Fitness': 'FITNESS',
        'Personal — Photography': 'PHOTOGRAPHY',
    }
    if name in mapping:
        return mapping[name]
    name = name.replace('Work — ', '').replace('Personal — ', '')
    return name.upper()

def extract_priority(task_raw: str) -> tuple[str, str]:
    """Extract priority tag from task text. Returns (priority, clean_text)."""
    task_raw = re.sub(r'\*+', '', task_raw).strip()
    match = re.match(r'\[(Hi(?:gh)?|Med(?:ium)?|Lo(?:w)?)\]\s*', task_raw, re.IGNORECASE)
    if match:
        raw_priority = match.group(1).lower()
        if raw_priority.startswith('hi'):
            priority = 'Hi'
        elif raw_priority.startswith('med'):
            priority = 'Med'
        else:
            priority = 'Lo'
        text = task_raw[match.end():].strip()
        return priority, text
    return 'Lo', task_raw.strip()

def parse_tasks():
    """Parse TASKS.md and extract open tasks organized by section with priorities."""
    tasks_file = DATA_DIR / "TASKS.md"
    if not tasks_file.exists():
        return []

    content = tasks_file.read_text()
    sections = []
    current_section = None
    current_section_raw = None
    current_tasks = []

    for line in content.splitlines():
        if line.startswith('## '):
            if current_section and current_tasks:
                sections.append({
                    'name': current_section,
                    'raw_name': current_section_raw,
                    'is_personal': 'personal' in current_section_raw.lower(),
                    'tasks': sorted(current_tasks, key=lambda t: t['priority_order'])
                })

            section_name = line[3:].strip()
            if section_name.lower() in ['done', 'waiting on']:
                current_section = None
                current_tasks = []
                break

            current_section_raw = section_name
            current_section = shorten_section(section_name)
            current_tasks = []

        elif line.strip().startswith('- [ ]') and current_section:
            task_raw = line.strip()[6:].strip()
            priority, text = extract_priority(task_raw)
            is_other_action = '[THEIR ACTION]' in text.upper() or "[TONY'S ACTION]" in text.upper()
            priority_order = {'Hi': 0, 'Med': 1, 'Lo': 2}

            current_tasks.append({
                'text': text,
                'original_text': task_raw,
                'priority': priority,
                'priority_order': priority_order[priority],
                'is_their_action': is_other_action
            })

    if current_section and current_tasks:
        sections.append({
            'name': current_section,
            'raw_name': current_section_raw,
            'is_personal': 'personal' in current_section_raw.lower(),
            'tasks': sorted(current_tasks, key=lambda t: t['priority_order'])
        })

    return sections


def parse_meeting_summary(filepath: Path) -> dict:
    """Parse a single meeting summary markdown file into structured data."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()

    meeting = {
        'title': '',
        'date': '',
        'source_url': '',
        'attendees': '',
        'summary': '',
        'key_decisions': [],
        'action_items': [],
        'open_questions': [],
        'filename': filepath.name,
    }

    # Extract title from H1
    for line in lines:
        if line.startswith('# ') and not line.startswith('## '):
            meeting['title'] = line[2:].strip()
            break

    # Extract metadata fields
    for line in lines:
        if line.startswith('**Date:**'):
            meeting['date'] = line.replace('**Date:**', '').strip()
        elif line.startswith('**Source:**'):
            # Extract URL from markdown link
            url_match = re.search(r'\((https?://[^)]+)\)', line)
            if url_match:
                meeting['source_url'] = url_match.group(1)
        elif line.startswith('**Attendees:**'):
            meeting['attendees'] = line.replace('**Attendees:**', '').strip()

    # Parse sections
    current_section = None
    section_lines = []

    for line in lines:
        if line.startswith('## '):
            # Save previous section
            if current_section and section_lines:
                _save_section(meeting, current_section, section_lines)
            current_section = line[3:].strip()
            section_lines = []
        elif current_section:
            section_lines.append(line)

    # Save last section
    if current_section and section_lines:
        _save_section(meeting, current_section, section_lines)

    return meeting


def _save_section(meeting: dict, section_name: str, lines: list[str]):
    """Save parsed section content into the meeting dict."""
    if section_name == 'Summary':
        meeting['summary'] = '\n'.join(lines).strip()
    elif section_name == 'Key Decisions':
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('- '):
                meeting['key_decisions'].append(stripped[2:])
    elif section_name == 'Action Items':
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('- [ ]') or stripped.startswith('- [x]'):
                is_done = stripped.startswith('- [x]')
                item_text = stripped[6:].strip()
                # Extract person name from bold
                person_match = re.match(r'\*\*(.+?)\*\*\s*[—–-]\s*(.*)', item_text)
                if person_match:
                    meeting['action_items'].append({
                        'person': person_match.group(1),
                        'text': person_match.group(2),
                        'done': is_done,
                    })
                else:
                    meeting['action_items'].append({
                        'person': '',
                        'text': item_text,
                        'done': is_done,
                    })
    elif section_name == 'Open Questions':
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('- '):
                meeting['open_questions'].append(stripped[2:])


def load_meeting_summaries(days_back: int = 7) -> list[dict]:
    """Load and parse meeting summaries from the last N days, newest first."""
    if not MEETING_SUMMARIES_DIR.exists():
        return []

    meetings = []
    cutoff = datetime.now().strftime('%Y-%m-%d')

    for filepath in sorted(MEETING_SUMMARIES_DIR.glob('*.md'), reverse=True):
        # Extract date from filename (YYYY-MM-DD prefix)
        date_match = re.match(r'^(\d{4}-\d{2}-\d{2})', filepath.name)
        if not date_match:
            continue

        file_date = date_match.group(1)

        # Only include meetings from the last N days
        try:
            meeting_dt = datetime.strptime(file_date, '%Y-%m-%d')
            days_diff = (datetime.now() - meeting_dt).days
            if days_diff > days_back:
                continue
        except ValueError:
            continue

        try:
            meeting = parse_meeting_summary(filepath)
            meetings.append(meeting)
        except Exception as e:
            print(f"Error parsing {filepath.name}: {e}")
            continue

    return meetings


def parse_investor_table():
    """Parse memory/glossary.md and extract investor universe table."""
    glossary_file = DATA_DIR / "memory" / "glossary.md"
    if not glossary_file.exists():
        return []

    content = glossary_file.read_text()
    investors = []

    in_investor_table = False
    for line in content.split('\n'):
        if '## Investor Universe' in line:
            in_investor_table = True
            continue

        if in_investor_table:
            if line.startswith('##') and 'Investor Universe' not in line:
                break
            if line.startswith('|') and not line.startswith('|---'):
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 4 and parts[0] != 'Name':
                    investors.append({
                        'name': parts[0],
                        'type': parts[1],
                        'status': parts[2],
                        'notes': parts[3]
                    })

    return investors

def get_recent_investor_activity(investor_names):
    """Extract recent mentions of investors from inbox.md and TASKS.md."""
    activity = []

    inbox_file = DATA_DIR / "inbox.md"
    if inbox_file.exists():
        content = inbox_file.read_text()
        for line in content.split('\n'):
            if line.strip() and not line.startswith('#'):
                for investor_name in investor_names:
                    if investor_name.lower() in line.lower():
                        activity.append({'text': line.strip(), 'source': 'INBOX'})
                        break

    tasks_file = DATA_DIR / "TASKS.md"
    if tasks_file.exists():
        content = tasks_file.read_text()
        for line in content.split('\n'):
            if line.strip().startswith('- ['):
                task_text = re.sub(r'- \[.\] ', '', line.strip())
                for investor_name in investor_names:
                    if investor_name.lower() in task_text.lower():
                        activity.append({'text': task_text, 'source': 'TASK'})
                        break

    return activity[:8]

def get_calendar_events():
    """Fetch today's calendar events with error handling."""
    try:
        events = get_todays_events(days_ahead=1)
        now = datetime.now()
        found_current = False

        for event in events:
            try:
                event_hour = int(event['start'].split(':')[0])
                event_minute = int(event['start'].split(':')[1].split()[0])
                is_pm = 'PM' in event['start']

                if is_pm and event_hour != 12:
                    event_hour += 12
                elif not is_pm and event_hour == 12:
                    event_hour = 0

                event_time = now.replace(hour=event_hour, minute=event_minute, second=0, microsecond=0)

                if event_time < now:
                    event['is_past'] = True
                    event['is_current'] = False
                elif not found_current:
                    event['is_current'] = True
                    event['is_past'] = False
                    found_current = True
                else:
                    event['is_past'] = False
                    event['is_current'] = False
            except:
                event['is_past'] = False
                event['is_current'] = False

        return {'success': True, 'events': events}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# === FLASK ROUTES ===

@app.route('/')
def dashboard():
    """Render the dashboard."""
    task_sections = parse_tasks()
    investors = parse_investor_table()
    investor_names = [inv['name'] for inv in investors]
    recent_activity = get_recent_investor_activity(investor_names)
    calendar_data = get_calendar_events()
    meetings = load_meeting_summaries(days_back=7)

    current_date = datetime.now().strftime("%B %d, %Y")
    refresh_time = datetime.now().strftime("%-I:%M %p")

    return render_template_string(TEMPLATE,
        current_date=current_date,
        refresh_time=refresh_time,
        task_sections=task_sections,
        calendar_data=calendar_data,
        meetings=meetings,
        investors=investors,
        recent_activity=recent_activity
    )

@app.route('/api/task/complete', methods=['POST'])
def complete_task():
    """Mark a task as complete in TASKS.md."""
    try:
        data = request.json
        task_text = data.get('task_text', '').strip()

        if not task_text:
            return jsonify({'ok': False, 'error': 'No task text provided'}), 400

        tasks_file = DATA_DIR / "TASKS.md"
        if not tasks_file.exists():
            return jsonify({'ok': False, 'error': 'TASKS.md not found'}), 404

        content = tasks_file.read_text()
        lines = content.split('\n')
        modified = False

        for i, line in enumerate(lines):
            if line.strip().startswith('- [ ]'):
                line_task_text = line.strip()[6:].strip()
                if line_task_text == task_text:
                    lines[i] = line.replace('- [ ]', '- [x]', 1)
                    modified = True
                    break

        if modified:
            tasks_file.write_text('\n'.join(lines))
            return jsonify({'ok': True})
        else:
            return jsonify({'ok': False, 'error': 'Task not found'}), 404

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/task/add', methods=['POST'])
def add_task():
    """Add a new task to TASKS.md under the specified section."""
    try:
        data = request.json
        task_text = data.get('task_text', '').strip()
        priority = data.get('priority', 'Med').strip()
        section = data.get('section', 'Work — Operations').strip()

        if not task_text:
            return jsonify({'ok': False, 'error': 'No task text provided'}), 400

        if priority not in ('Hi', 'Med', 'Lo'):
            priority = 'Med'

        tasks_file = DATA_DIR / "TASKS.md"
        if not tasks_file.exists():
            return jsonify({'ok': False, 'error': 'TASKS.md not found'}), 404

        content = tasks_file.read_text()
        lines = content.split('\n')

        new_line = f"- [ ] **[{priority}]** {task_text}"

        # Find the target section and insert after heading
        inserted = False
        for i, line in enumerate(lines):
            if line.startswith('## ') and line[3:].strip() == section:
                lines.insert(i + 1, new_line)
                inserted = True
                break

        # Fallback: insert under Work — Operations
        if not inserted:
            for i, line in enumerate(lines):
                if line.startswith('## ') and 'Operations' in line:
                    lines.insert(i + 1, new_line)
                    inserted = True
                    break

        # Last resort: insert after the first ## heading
        if not inserted:
            for i, line in enumerate(lines):
                if line.startswith('## '):
                    lines.insert(i + 1, new_line)
                    inserted = True
                    break

        if inserted:
            tasks_file.write_text('\n'.join(lines))
            return jsonify({'ok': True})
        else:
            return jsonify({'ok': False, 'error': 'Could not find section'}), 404

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/task/priority', methods=['POST'])
def change_priority():
    """Change a task's priority in TASKS.md."""
    try:
        data = request.json
        task_text = data.get('task_text', '').strip()
        new_priority = data.get('priority', '').strip()

        if not task_text or not new_priority:
            return jsonify({'ok': False, 'error': 'Missing task_text or priority'}), 400

        if new_priority not in ('Hi', 'Med', 'Lo'):
            return jsonify({'ok': False, 'error': 'Invalid priority'}), 400

        tasks_file = DATA_DIR / "TASKS.md"
        if not tasks_file.exists():
            return jsonify({'ok': False, 'error': 'TASKS.md not found'}), 404

        content = tasks_file.read_text()
        lines = content.split('\n')
        modified = False

        for i, line in enumerate(lines):
            if line.strip().startswith('- [ ]'):
                line_task_text = line.strip()[6:].strip()
                if line_task_text == task_text:
                    # Remove old priority tag (any variant)
                    cleaned = re.sub(r'\*{0,2}\[(Hi(?:gh)?|Med(?:ium)?|Lo(?:w)?)\]\*{0,2}\s*', '', line_task_text, flags=re.IGNORECASE).strip()
                    indent = line[:len(line) - len(line.lstrip())]
                    lines[i] = f"{indent}- [ ] **[{new_priority}]** {cleaned}"
                    modified = True
                    break

        if modified:
            tasks_file.write_text('\n'.join(lines))
            return jsonify({'ok': True})
        else:
            return jsonify({'ok': False, 'error': 'Task not found'}), 404

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/meeting/archive', methods=['POST'])
def archive_meeting():
    """Move a meeting summary to the archive folder."""
    try:
        data = request.json
        filename = data.get('filename', '').strip()

        if not filename:
            return jsonify({'ok': False, 'error': 'No filename provided'}), 400

        # Sanitize filename to prevent path traversal
        filename = Path(filename).name

        source = MEETING_SUMMARIES_DIR / filename
        if not source.exists():
            return jsonify({'ok': False, 'error': 'Meeting file not found'}), 404

        MEETING_ARCHIVE_DIR.mkdir(exist_ok=True)
        dest = MEETING_ARCHIVE_DIR / filename
        source.rename(dest)

        return jsonify({'ok': True})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AREC Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif;
            background: #ffffff;
            color: #1f2937;
            line-height: 1.5;
            padding: 20px;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            padding-bottom: 12px;
            border-bottom: 1px solid #e5e7eb;
        }

        .header-left {
            font-size: 20px;
            font-weight: 600;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .current-date {
            font-size: 14px;
            color: #6b7280;
        }

        .refresh-btn {
            background: #3b82f6;
            color: white;
            border: none;
            padding: 6px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
        }

        .refresh-btn:hover {
            background: #2563eb;
        }

        .refresh-time {
            font-size: 12px;
            color: #9ca3af;
            margin-bottom: 16px;
        }

        .dashboard {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1px;
            background: #e5e7eb;
            border: 1px solid #e5e7eb;
        }

        .column {
            background: white;
            padding: 20px;
            min-height: 80vh;
            max-height: 85vh;
            overflow-y: auto;
        }

        .column-header {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #6b7280;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid #f3f4f6;
        }

        /* Tasks */
        .task-section {
            margin-bottom: 24px;
        }

        .task-section-label {
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #9ca3af;
            margin-bottom: 8px;
        }

        .task-section.personal .task-section-label,
        .task-section.personal .task-row {
            opacity: 0.7;
        }

        .section-divider {
            height: 1px;
            background: #d1d5db;
            margin: 24px 0;
        }

        .task-row {
            display: flex;
            gap: 8px;
            padding: 8px 0;
            border-bottom: 1px solid #f9fafb;
            align-items: flex-start;
            transition: opacity 0.2s;
        }

        .task-row.completed {
            opacity: 0;
            pointer-events: none;
        }

        .task-priority {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            font-family: 'SF Mono', Monaco, monospace;
            flex-shrink: 0;
            margin-top: 2px;
            cursor: pointer;
            transition: all 0.15s;
        }

        .task-priority:hover {
            transform: scale(1.1);
            box-shadow: 0 1px 3px rgba(0,0,0,0.15);
        }

        .task-priority.hi {
            background: #fee2e2;
            color: #991b1b;
        }

        .task-priority.med {
            background: #fef9c3;
            color: #854d0e;
        }

        .task-priority.lo {
            background: #f1f5f9;
            color: #64748b;
        }

        .task-checkbox {
            width: 16px;
            height: 16px;
            border: 1.5px solid #d1d5db;
            border-radius: 3px;
            flex-shrink: 0;
            margin-top: 2px;
            cursor: pointer;
            transition: all 0.15s;
        }

        .task-checkbox:hover {
            border-color: #3b82f6;
            background: #eff6ff;
        }

        .task-text {
            flex: 1;
            font-size: 14px;
            color: #374151;
            line-height: 1.4;
        }

        .task-row.their-action .task-text {
            color: #9ca3af;
            font-style: italic;
        }

        .task-row.their-action .task-checkbox,
        .task-row.their-action .task-priority {
            display: none;
        }

        /* Add Task Form */
        .add-task-bar {
            display: flex;
            gap: 6px;
            margin-bottom: 16px;
            padding-bottom: 16px;
            border-bottom: 1px solid #e5e7eb;
            flex-wrap: wrap;
        }

        .add-task-input {
            flex: 1;
            min-width: 120px;
            padding: 6px 10px;
            border: 1px solid #d1d5db;
            border-radius: 5px;
            font-size: 13px;
            font-family: inherit;
            outline: none;
            transition: border-color 0.15s;
        }

        .add-task-input:focus {
            border-color: #3b82f6;
        }

        .add-task-select {
            padding: 6px 8px;
            border: 1px solid #d1d5db;
            border-radius: 5px;
            font-size: 12px;
            background: white;
            color: #374151;
            cursor: pointer;
        }

        .add-task-btn {
            padding: 6px 14px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.15s;
        }

        .add-task-btn:hover {
            background: #2563eb;
        }

        /* Calendar */
        .event-card {
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 10px;
        }

        .event-card.all-day {
            background: #f9fafb;
            border-style: dashed;
        }

        .event-card.past {
            opacity: 0.5;
        }

        .event-card.current {
            background: #eff6ff;
            border-color: #3b82f6;
        }

        .event-time {
            font-weight: 600;
            font-size: 13px;
            color: #111827;
            margin-bottom: 4px;
        }

        .event-title {
            font-size: 14px;
            color: #374151;
            margin-bottom: 6px;
        }

        .event-attendees {
            font-size: 12px;
            color: #6b7280;
        }

        .unavailable {
            color: #9ca3af;
            font-size: 14px;
            font-style: italic;
        }

        /* Meeting Summaries */
        .meeting-card {
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            margin-bottom: 14px;
            overflow: hidden;
            transition: border-color 0.15s;
        }

        .meeting-card:hover {
            border-color: #d1d5db;
        }

        .meeting-card-header {
            padding: 12px 14px 10px;
            cursor: pointer;
            user-select: none;
        }

        .meeting-date-group {
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #9ca3af;
            margin-bottom: 12px;
            margin-top: 8px;
        }

        .meeting-date-group:first-child {
            margin-top: 0;
        }

        .meeting-title {
            font-size: 14px;
            font-weight: 600;
            color: #111827;
            margin-bottom: 4px;
            line-height: 1.3;
        }

        .meeting-meta {
            font-size: 12px;
            color: #6b7280;
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .meeting-attendee-count {
            font-size: 11px;
            color: #9ca3af;
        }

        .meeting-expand-icon {
            float: right;
            font-size: 12px;
            color: #9ca3af;
            margin-top: 2px;
            transition: transform 0.2s;
        }

        .meeting-card.expanded .meeting-expand-icon {
            transform: rotate(90deg);
        }

        .meeting-detail {
            display: none;
            padding: 0 14px 14px;
            border-top: 1px solid #f3f4f6;
        }

        .meeting-card.expanded .meeting-detail {
            display: block;
        }

        .meeting-summary-text {
            font-size: 13px;
            color: #374151;
            line-height: 1.6;
            margin-top: 10px;
            margin-bottom: 12px;
        }

        .meeting-summary-text p {
            margin-bottom: 8px;
        }

        .meeting-section-label {
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #9ca3af;
            margin-top: 12px;
            margin-bottom: 6px;
        }

        .meeting-decision,
        .meeting-question {
            font-size: 13px;
            color: #374151;
            padding: 4px 0;
            padding-left: 12px;
            border-left: 2px solid #e5e7eb;
            margin-bottom: 4px;
            line-height: 1.4;
        }

        .meeting-action-item {
            font-size: 13px;
            color: #374151;
            padding: 4px 0;
            display: flex;
            gap: 6px;
            line-height: 1.4;
        }

        .meeting-action-check {
            color: #d1d5db;
            flex-shrink: 0;
        }

        .meeting-action-check.done {
            color: #22c55e;
        }

        .meeting-action-person {
            font-weight: 600;
            color: #111827;
        }

        .meeting-source-link {
            display: inline-block;
            font-size: 11px;
            color: #6b7280;
            text-decoration: none;
            margin-top: 10px;
            padding: 3px 8px;
            background: #f9fafb;
            border-radius: 4px;
            transition: background 0.15s;
        }

        .meeting-source-link:hover {
            background: #f3f4f6;
            color: #374151;
        }

        .meeting-archive-btn {
            display: inline-block;
            font-size: 11px;
            color: #6b7280;
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 4px;
            padding: 3px 10px;
            margin-top: 10px;
            margin-left: 8px;
            cursor: pointer;
            transition: all 0.15s;
        }

        .meeting-archive-btn:hover {
            background: #dcfce7;
            border-color: #86efac;
            color: #166534;
        }

        .no-meetings {
            color: #9ca3af;
            font-size: 14px;
            font-style: italic;
        }

        /* Investors */
        .investor-section {
            margin-bottom: 32px;
        }

        .investor-section-title {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #6b7280;
            margin-bottom: 12px;
        }

        .investor-row {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 8px;
            padding: 8px 0;
            border-bottom: 1px solid #f9fafb;
            font-size: 13px;
        }

        .investor-name {
            font-weight: 500;
            color: #111827;
        }

        .investor-status {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            white-space: nowrap;
        }

        .investor-status.committed {
            background: #dcfce7;
            color: #166534;
        }

        .investor-status.hot-prospect {
            background: #ffedd5;
            color: #9a3412;
        }

        .investor-status.prospect {
            background: #dbeafe;
            color: #1e40af;
        }

        .investor-status.current {
            background: #f3e8ff;
            color: #6b21a8;
        }

        .investor-notes {
            grid-column: 1 / -1;
            font-size: 12px;
            color: #6b7280;
            padding-left: 0;
        }

        .activity-item {
            padding: 8px 0;
            border-bottom: 1px solid #f9fafb;
            font-size: 13px;
            color: #374151;
        }

        .activity-tag {
            display: inline-block;
            font-size: 10px;
            color: #9ca3af;
            background: #f9fafb;
            padding: 2px 6px;
            border-radius: 3px;
            margin-right: 6px;
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-left">AREC — Oscar Vasquez</div>
        <div class="header-right">
            <div class="current-date">{{ current_date }}</div>
            <button class="refresh-btn" onclick="location.reload()">Refresh</button>
        </div>
    </div>
    <div class="refresh-time">Refreshed: {{ refresh_time }}</div>

    <div class="dashboard">
        <!-- Column 1: Tasks -->
        <div class="column">
            <div class="column-header">Tasks</div>

            <div class="add-task-bar">
                <input type="text" class="add-task-input" id="newTaskInput" placeholder="New task..." onkeydown="if(event.key==='Enter') addTask()">
                <select class="add-task-select" id="newTaskPriority">
                    <option value="Hi">Hi</option>
                    <option value="Med" selected>Med</option>
                    <option value="Lo">Lo</option>
                </select>
                <select class="add-task-select" id="newTaskSection">
                    {% for section in task_sections %}
                    <option value="{{ section.raw_name }}">{{ section.name }}</option>
                    {% endfor %}
                </select>
                <button class="add-task-btn" onclick="addTask()">Add</button>
            </div>

            {% for section in task_sections %}
                {% if loop.index > 1 and section.is_personal and not task_sections[loop.index0 - 1].is_personal %}
                    <div class="section-divider"></div>
                {% endif %}

                <div class="task-section {% if section.is_personal %}personal{% endif %}">
                    <div class="task-section-label">{{ section.name }}</div>
                    {% for task in section.tasks %}
                    <div class="task-row {% if task.is_their_action %}their-action{% endif %}" data-task-text="{{ task.original_text }}">
                        {% if not task.is_their_action %}
                        <span class="task-priority {{ task.priority.lower() }}" data-priority="{{ task.priority }}" onclick="cyclePriority(event, this)">{{ task.priority }}</span>
                        <div class="task-checkbox" onclick="completeTask(this)"></div>
                        <div class="task-text">{{ task.text }}</div>
                        {% else %}
                        <div class="task-text">{{ task.text }}</div>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
            {% endfor %}
        </div>

        <!-- Column 2: Today -->
        <div class="column">
            <div class="column-header">Today</div>
            {% if calendar_data.success %}
                {% set all_day_events = calendar_data.events|selectattr('is_all_day')|list %}
                {% set timed_events = calendar_data.events|rejectattr('is_all_day')|list %}

                {% for event in all_day_events %}
                <div class="event-card all-day">
                    <div class="event-time">All Day</div>
                    <div class="event-title">{{ event.title }}</div>
                </div>
                {% endfor %}

                {% for event in timed_events %}
                <div class="event-card {% if event.is_past %}past{% endif %} {% if event.is_current %}current{% endif %}">
                    <div class="event-time">{{ event.start }} – {{ event.end }}</div>
                    <div class="event-title">{{ event.title }}</div>
                    {% if event.organizer or event.attendees %}
                    <div class="event-attendees">
                        {% if event.organizer %}{{ event.organizer }}{% endif %}
                        {% if event.attendees %}
                            {% if event.organizer %} · {% endif %}
                            {{ event.attendees[:3]|join(', ') }}
                            {% if event.attendees|length > 3 %}+{{ event.attendees|length - 3 }} more{% endif %}
                        {% endif %}
                    </div>
                    {% endif %}
                </div>
                {% endfor %}
            {% else %}
                <div class="unavailable">Calendar unavailable</div>
            {% endif %}
        </div>

        <!-- Column 3: Meetings -->
        <div class="column">
            <div class="column-header">Recent Meetings</div>
            {% if meetings %}
                {% set ns = namespace(current_date='') %}
                {% for meeting in meetings %}
                    {% if meeting.date != ns.current_date %}
                        {% set ns.current_date = meeting.date %}
                        <div class="meeting-date-group">{{ meeting.date }}</div>
                    {% endif %}

                    <div class="meeting-card" onclick="toggleMeeting(this)">
                        <div class="meeting-card-header">
                            <span class="meeting-expand-icon">▶</span>
                            <div class="meeting-title">{{ meeting.title }}</div>
                            <div class="meeting-meta">
                                {% if meeting.attendees %}
                                <span class="meeting-attendee-count">{{ meeting.attendees }}</span>
                                {% endif %}
                            </div>
                        </div>
                        <div class="meeting-detail">
                            {% if meeting.summary %}
                            <div class="meeting-summary-text">
                                {% for para in meeting.summary.split('\n\n') %}
                                    {% if para.strip() %}
                                    <p>{{ para.strip() }}</p>
                                    {% endif %}
                                {% endfor %}
                            </div>
                            {% endif %}

                            {% if meeting.key_decisions %}
                            <div class="meeting-section-label">Decisions</div>
                            {% for decision in meeting.key_decisions %}
                            <div class="meeting-decision">{{ decision }}</div>
                            {% endfor %}
                            {% endif %}

                            {% if meeting.action_items %}
                            <div class="meeting-section-label">Action Items</div>
                            {% for item in meeting.action_items %}
                            <div class="meeting-action-item">
                                <span class="meeting-action-check {% if item.done %}done{% endif %}">
                                    {% if item.done %}✓{% else %}○{% endif %}
                                </span>
                                <span>
                                    {% if item.person %}<span class="meeting-action-person">{{ item.person }}</span> — {% endif %}{{ item.text }}
                                </span>
                            </div>
                            {% endfor %}
                            {% endif %}

                            {% if meeting.open_questions %}
                            <div class="meeting-section-label">Open Questions</div>
                            {% for question in meeting.open_questions %}
                            <div class="meeting-question">{{ question }}</div>
                            {% endfor %}
                            {% endif %}

                            {% if meeting.source_url %}
                            <a href="{{ meeting.source_url }}" target="_blank" class="meeting-source-link">View in Notion →</a>
                            {% endif %}
                            <button class="meeting-archive-btn" data-filename="{{ meeting.filename }}" onclick="archiveMeeting(event, this)">Archive ✓</button>
                        </div>
                    </div>
                {% endfor %}
            {% else %}
                <div class="no-meetings">No meeting summaries found</div>
            {% endif %}
        </div>

        <!-- Column 4: Investors -->
        <div class="column">
            <div class="column-header">Investors</div>

            <div class="investor-section">
                <div class="investor-section-title">Investor Pipeline</div>
                {% for investor in investors %}
                <div class="investor-row">
                    <div class="investor-name">{{ investor.name }}</div>
                    <div class="investor-status {{ investor.status.lower().replace(' ', '-').replace('→', '').strip() }}">
                        {{ investor.status }}
                    </div>
                    {% if investor.notes %}
                    <div class="investor-notes">{{ investor.notes }}</div>
                    {% endif %}
                </div>
                {% endfor %}
            </div>

            <div class="investor-section">
                <div class="investor-section-title">Recent Activity</div>
                {% for item in recent_activity %}
                <div class="activity-item">
                    <span class="activity-tag">{{ item.source }}</span>
                    {{ item.text }}
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <script>
        function completeTask(checkbox) {
            const taskRow = checkbox.closest('.task-row');
            const taskText = taskRow.getAttribute('data-task-text');

            fetch('/api/task/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_text: taskText })
            })
            .then(response => response.json())
            .then(data => {
                if (data.ok) {
                    taskRow.classList.add('completed');
                    setTimeout(() => { taskRow.style.display = 'none'; }, 200);
                } else {
                    alert('Failed to complete task: ' + data.error);
                }
            })
            .catch(error => { alert('Error completing task'); });
        }

        function addTask() {
            const input = document.getElementById('newTaskInput');
            const priority = document.getElementById('newTaskPriority').value;
            const section = document.getElementById('newTaskSection').value;
            const taskText = input.value.trim();

            if (!taskText) return;

            fetch('/api/task/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_text: taskText, priority: priority, section: section })
            })
            .then(response => response.json())
            .then(data => {
                if (data.ok) {
                    input.value = '';
                    location.reload();
                } else {
                    alert('Failed to add task: ' + data.error);
                }
            })
            .catch(error => { alert('Error adding task'); });
        }

        function cyclePriority(event, pill) {
            event.stopPropagation();
            const taskRow = pill.closest('.task-row');
            const taskText = taskRow.getAttribute('data-task-text');
            const current = pill.getAttribute('data-priority');

            const cycle = { 'Hi': 'Med', 'Med': 'Lo', 'Lo': 'Hi' };
            const newPriority = cycle[current];

            fetch('/api/task/priority', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_text: taskText, priority: newPriority })
            })
            .then(response => response.json())
            .then(data => {
                if (data.ok) {
                    pill.setAttribute('data-priority', newPriority);
                    pill.textContent = newPriority;
                    pill.className = 'task-priority ' + newPriority.toLowerCase();
                } else {
                    alert('Failed to change priority: ' + data.error);
                }
            })
            .catch(error => { alert('Error changing priority'); });
        }

        function toggleMeeting(card) {
            if (event.target.tagName === 'A' || event.target.tagName === 'BUTTON') return;
            card.classList.toggle('expanded');
        }

        function archiveMeeting(event, btn) {
            event.stopPropagation();
            const filename = btn.getAttribute('data-filename');
            const card = btn.closest('.meeting-card');

            fetch('/api/meeting/archive', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename })
            })
            .then(response => response.json())
            .then(data => {
                if (data.ok) {
                    card.style.transition = 'opacity 0.3s';
                    card.style.opacity = '0';
                    setTimeout(() => { card.style.display = 'none'; }, 300);
                } else {
                    alert('Failed to archive: ' + data.error);
                }
            })
            .catch(error => { alert('Error archiving meeting'); });
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    print("Starting AREC Dashboard on http://localhost:3001")
    app.run(host='127.0.0.1', port=3001, debug=False)
