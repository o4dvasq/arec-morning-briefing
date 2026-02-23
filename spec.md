

---

# AREC Morning Briefing — Complete Application Specification

**Version:** 1.0
**Date:** February 23, 2026
**Author:** Oscar Vasquez, COO — Avila Real Estate Capital
**Status:** Production (running on Oscar's work iMac)

---

## 1. Purpose

An automated daily morning briefing system that combines real-time Microsoft 365 data (calendar, email, Teams chat) with a persistent institutional memory system (markdown files maintained by the Claude Productivity app), synthesized by Claude AI and delivered as a formatted Slack DM at 5:00 AM Pacific every morning.

The goal is to replicate the output of a trusted chief of staff: a concise, intelligent, narrative briefing that surfaces what matters, flags action items, and connects live data to institutional context — without over-inferring connections that aren't explicitly supported by the source data.

---

## 2. Architecture Overview

DATA SOURCES ├── Microsoft Graph API: Calendar events, Outlook email, Teams chat messages └── Dropbox (local sync): TASKS.md, inbox.md, memory/projects/*.md, memory/people/*.md, memory/context/*.md

PROCESSING ENGINE memory_reader.py → prompt_builder.py → generator.py (parse markdown)   (assemble prompt)   (Claude API)

DELIVERY slack_sender.py → Slack DM (@AREC Briefing bot)

FEEDBACK LOOP User DMs bot → slack_listener.py (Flask port 3000) → appends to inbox.md → Claude Productivity processes



Scheduler: macOS launchd fires main.py at 5:00 AM daily
Runtime: ~15 seconds end-to-end
Platform: macOS native (no Docker)

---

## 3. Directory Structure

~/arec-morning-briefing/ ├── main.py ├── config.yaml ├── requirements.txt ├── .env ├── .env.example ├── .gitignore ├── README.md ├── SPEC.md ├── auth/ │   ├── **init**.py │   └── graph_auth.py ├── sources/ │   ├── **init**.py │   ├── ms_graph.py │   └── memory_reader.py ├── briefing/ │   ├── **init**.py │   ├── prompt_builder.py │   └── generator.py ├── delivery/ │   ├── **init**.py │   ├── slack_sender.py │   └── slack_listener.py └── scripts/ ├── setup.sh ├── test_run.sh ├── start_listener.sh ├── com.arec.morningbriefing.plist └── com.arec.slacklistener.plist



---

## 4. Component Details

### main.py — Orchestrator
- Loads config.yaml and .env
- Calls each source module in sequence
- Passes all data to briefing generator
- Delivers result to Slack
- Writes logs to ~/Library/Logs/arec-morning-briefing.log

### auth/graph_auth.py — Microsoft Authentication
- Uses MSAL PublicClientApplication with device code flow
- Token cache stored at ~/.arec_briefing_token_cache.json
- Silent refresh on each run
- Run once interactively: python3 auth/graph_auth.py --setup
- Scopes: Calendars.Read, Mail.Read, Chat.Read, Tasks.Read, User.Read

### sources/ms_graph.py — Microsoft Graph Data
- get_todays_events() — calendar events for today via calendarView
- get_recent_emails() — last 18 hours of inbox messages
- get_recent_teams_messages() — recent Teams DM/chat activity
- Handles Microsoft 7-decimal timestamp format
- All times localized to America/Los_Angeles

### sources/memory_reader.py — Dropbox Memory Parser
- Base path: ~/Dropbox/Tech/ClaudeProductivity (expanduser for portability)
- _extract_open_tasks() — parses TASKS.md, groups by section, stops at Done
- _extract_inbox_items() — reads inbox.md capture queue (cap 10 items)
- _load_people_files() — loads all .md files from memory/people/ (first 400 chars each)

### briefing/prompt_builder.py — Prompt Assembly
- SYSTEM_PROMPT defines persona, style rules, inference constraints
- Only connects meeting/person to topic at 90%+ confidence from source data
- No emojis. Bold for names and times. Short paragraphs for mobile.
- Sections: Schedule → Email Action Items → Open Tasks → Headline
- People context only surfaced for attendees explicitly in today's calendar

### briefing/generator.py — Claude API
- Model: claude-sonnet-4-6
- Max tokens: 1500
- Target output: ~400 words, mobile-formatted Slack markdown

### delivery/slack_sender.py — Slack Delivery
- Opens DM via conversations.open
- Posts with mrkdwn: true
- Scopes needed: chat:write, im:write, im:history

### delivery/slack_listener.py — Feedback Loop
- Flask app on port 3000
- Handles Slack URL verification challenge
- Listens for message.im events
- Appends to inbox.md: - [BRIEFING FEEDBACK YYYY-MM-DD]: message text
- Responds: "Got it, added to inbox ✓"
- Exposed publicly via ngrok

---

## 5. Configuration — config.yaml

briefing:
  delivery_time: "05:00"
  timezone: "America/Los_Angeles"
  calendar_days_ahead: 1
  email_scan_hours: 18
  email_max_results: 15

memory:
  base_path: "~/Dropbox/Tech/ClaudeProductivity"
  files:
    tasks: "TASKS.md"
    inbox: "inbox.md"
    fund_ii: "memory/projects/arec-fund-ii.md"
    company: "memory/context/company.md"
    glossary: "memory/glossary.md"
    claude_context: "CLAUDE.md"
  people_dir: "memory/people"

delivery:
  platform: "slack"

logging:
  path: "~/Library/Logs/arec-morning-briefing.log"
  level: "INFO"

---

## 6. Environment Variables

| Variable          | Description                | Source                           |
| ----------------- | -------------------------- | -------------------------------- |
| ANTHROPIC_API_KEY | Anthropic API key          | console.anthropic.com            |
| AZURE_CLIENT_ID   | Azure app client ID        | portal.azure.com                 |
| AZURE_TENANT_ID   | Azure tenant ID            | portal.azure.com                 |
| MS_USER_ID        | Microsoft user object ID   | printed by graph_auth.py --setup |
| SLACK_BOT_TOKEN   | Slack bot token (xoxb-...) | api.slack.com/apps               |
| SLACK_USER_ID     | Slack member ID (U...)     | Slack profile → Copy member ID   |

Note: AZURE_CLIENT_SECRET not used — app uses PublicClientApplication device flow.

---

## 7. External Services

### Microsoft Azure App Registration
- App name: AREC Morning Briefing - Oscar
- Client ID: d58c6152-9b86-4cbf-828f-0ce61a746798
- Tenant ID: ebd42ab2-7f1c-4d40-8b44-f5ecc51d2659
- Tenant: Avila Capital LLC (single tenant)
- Auth type: Public client / device code flow
- Allow public client flows: Yes (required setting)
- API Permissions (all Delegated): Calendars.Read, Mail.Read, Chat.Read, Tasks.Read, User.Read
- Admin consent: Granted by Avila Capital IT admin

### Slack App
- App name: AREC Briefing
- Bot Token Scopes: chat:write, im:write, im:history, channels:write, groups:write
- Event Subscriptions: Enabled — bot event: message.im
- Request URL: https://[ngrok-url]/slack/events (update when ngrok restarts)
- App Home: Messages Tab on, users can send messages enabled

### Anthropic
- Model: claude-sonnet-4-6
- No separate app registration — uses Oscar's existing API key

---

## 8. Memory File System

Base path: ~/Dropbox/Tech/ClaudeProductivity/

| File                            | Purpose                                               |
| ------------------------------- | ----------------------------------------------------- |
| TASKS.md                        | Open tasks by category — surfaced in briefing         |
| inbox.md                        | Capture queue — feedback from Slack writes here       |
| memory/projects/arec-fund-ii.md | Fund II status and context                            |
| memory/context/company.md       | AREC company overview                                 |
| memory/people/*.md              | One file per key person — relationship context        |
| CLAUDE.md                       | Master context: people index, deal index, preferences |
| memory/glossary.md              | Terms and acronyms                                    |

Feedback loop: User DMs bot → appended to inbox.md → Claude Productivity processes on next run → updated memory flows into next briefing.

---

## 9. Scheduling

### Main Briefing
- Plist: ~/Library/LaunchAgents/com.arec.morningbriefing.plist
- Trigger: 5:00 AM daily (StartCalendarInterval)
- Requirement: Mac must be awake

### Slack Listener
- Plist: ~/Library/LaunchAgents/com.arec.slacklistener.plist
- Starts on login, kept alive automatically

---

## 10. Known Limitations

| Item                      | Detail                       | Fix                                                    |
| ------------------------- | ---------------------------- | ------------------------------------------------------ |
| Microsoft token expiry    | ~90 days                     | Run python3 auth/graph_auth.py --setup                 |
| ngrok URL rotation        | Changes on restart           | Update Slack Event Subscriptions URL, or upgrade ngrok |
| Mac must be awake at 5 AM | launchd won't fire if asleep | Keep Mac on overnight                                  |
| Python 3.9 SSL warning    | Harmless urllib3 warning     | Upgrade to Python 3.11+ when convenient                |

---

## 11. Python Dependencies

anthropic>=0.25.0
msal>=1.28.0
requests>=2.31.0
pyyaml>=6.0
python-dotenv>=1.0.0
slack-sdk>=3.27.0
flask>=3.0.0

---

## 12. Rebuild From Scratch
```bash
git clone https://github.com/YOUR_USERNAME/arec-morning-briefing.git
cd arec-morning-briefing
pip3 install -r requirements.txt
cp .env.example .env
nano .env
python3 auth/graph_auth.py --setup
bash scripts/test_run.sh
bash scripts/setup.sh
brew install ngrok
bash scripts/start_listener.sh
ngrok http 3000
# Copy ngrok URL into Slack Event Subscriptions Request URL
```

---

## 13. GitHub Setup
```bash
cd ~/arec-morning-briefing

cat > .gitignore << 'EOF'
.env
__pycache__/
*.pyc
*.pyo
.DS_Store
*.log
EOF

git init
git add .
git commit -m "Initial commit — AREC Morning Briefing v1.0"

# Create private repo at github.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/arec-morning-briefing.git
git branch -M main
git push -u origin main
```

Never commit: .env, token cache file, log files.

---

## 14. Docker Decision

Docker is not appropriate for this application. The app reads local Dropbox files,
uses macOS launchd for scheduling, and stores auth tokens in the home directory.
Containerizing would require volume mounts for all three, add complexity with no
reliability benefit, and break the seamless Dropbox integration. Native macOS is correct.

---

## 15. Future Enhancements

| Enhancement                                     | Effort | Value  |
| ----------------------------------------------- | ------ | ------ |
| Fixed ngrok domain or migrate listener to cloud | Low    | High   |
| Teams chat reader (already scaffolded)          | Low    | High   |
| Weekly summary briefing Friday PM               | Medium | Medium |
| Slack feedback processed by Claude inline       | Medium | High   |
| Voice delivery via text-to-speech               | Medium | Medium |
| Send to both Slack and email                    | Low    | Low    |