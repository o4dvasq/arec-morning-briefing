# AREC Morning Briefing

Automated 5 AM daily briefing delivered to Slack. Combines live Microsoft 365 data
with Claude Productivity memory files, synthesized by Claude AI.

## Quick Start

# 1. Install dependencies
pip3 install -r requirements.txt

# 2. Configure credentials
cp .env.example .env
nano .env

# 3. Authenticate with Microsoft (one-time)
python3 auth/graph_auth.py --setup

# 4. Test a full run
bash scripts/test_run.sh

# 5. Install the 5 AM scheduler
bash scripts/setup.sh

## Slack Setup (5 minutes)
1. Go to api.slack.com/apps → Create New App → From Scratch
2. Name: AREC Briefing — pick your workspace
3. OAuth & Permissions → add scope: chat:write
4. Install to Workspace → copy the Bot User OAuth Token (xoxb-...)
5. Your User ID: click your name in Slack → Profile → Member ID (starts with U)
6. Add both to .env

## Azure Setup (5 minutes)
1. portal.azure.com → Azure Active Directory → App registrations → New
2. Name: AREC Morning Briefing
3. Supported account types: Accounts in this organizational directory only
4. Redirect URI: Leave blank (not needed for device flow)
5. Note your Client ID and Tenant ID from the Overview page
6. API permissions → Add: Calendars.Read, Mail.Read, User.Read, Tasks.Read
7. Grant admin consent for your organization
8. Add both Client ID and Tenant ID to .env

## Slack Feedback Setup (Optional)

Enable two-way feedback: DM the AREC Briefing bot and it writes to inbox.md automatically.

### Prerequisites
```bash
# Install ngrok to expose localhost to Slack
brew install ngrok
```

### Setup Steps

1. **Start the listener locally**
   ```bash
   bash scripts/start_listener.sh
   ```

2. **Expose localhost with ngrok**
   ```bash
   ngrok http 3000
   ```
   Copy the HTTPS forwarding URL (e.g., https://abc123.ngrok.io)

3. **Configure Slack Event Subscriptions**
   - Go to api.slack.com/apps → AREC Briefing → Event Subscriptions
   - Enable Events: ON
   - Request URL: `https://your-ngrok-url/slack/events`
   - Wait for "Verified ✓" checkmark
   - Subscribe to bot events: `message.im`
   - Save Changes

4. **Add OAuth scope**
   - OAuth & Permissions → Bot Token Scopes
   - Add scope: `im:history`
   - Reinstall the app to your workspace

5. **Test it**
   - DM the AREC Briefing bot in Slack: "Test feedback message"
   - Check ~/Dropbox/Tech/ClaudeProductivity/inbox.md
   - You should see: `- [BRIEFING FEEDBACK 2026-02-23]: Test feedback message`

6. **Install as a persistent service (optional)**
   ```bash
   # Edit the plist to replace PROJECT_DIR_PLACEHOLDER
   sed "s|PROJECT_DIR_PLACEHOLDER|$HOME/arec-morning-briefing|g" \
       scripts/com.arec.slacklistener.plist > \
       ~/Library/LaunchAgents/com.arec.slacklistener.plist

   # Load the service
   launchctl load ~/Library/LaunchAgents/com.arec.slacklistener.plist
   ```

   Note: You'll need a permanent ngrok URL or deploy to a server for production use.

### Logs
```bash
tail -f ~/Library/Logs/arec-slack-listener.log
```

## Memory Files
The briefing reads from ~/Dropbox/Tech/ClaudeProductivity/ automatically.
Keep editing your markdown files as usual — next morning's briefing reflects latest state.

## Logs
tail -f ~/Library/Logs/arec-morning-briefing.log
