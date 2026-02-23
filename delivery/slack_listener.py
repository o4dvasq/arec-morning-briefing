"""
Slack feedback listener — receives DMs sent to the AREC Briefing bot
and appends them to inbox.md for processing in future briefings.
"""

import os
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

INBOX_PATH = Path("~/Dropbox/Tech/ClaudeProductivity/inbox.md").expanduser()


@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.json

    # Handle Slack URL verification challenge
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    # Handle incoming messages
    if data.get("type") == "event_callback":
        event = data.get("event", {})

        # Only process direct messages (message.im)
        if event.get("type") == "message" and event.get("channel_type") == "im":
            # Ignore bot messages and message edits
            if event.get("subtype") is None and "bot_id" not in event:
                message_text = event.get("text", "").strip()
                if message_text:
                    append_to_inbox(message_text)
                    # Respond to user
                    return jsonify({"text": "Got it, added to inbox ✓"})

    return jsonify({"status": "ok"})


def append_to_inbox(text: str):
    """Append feedback message to inbox.md with timestamp."""
    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"- [BRIEFING FEEDBACK {today}]: {text}\n"

    # Ensure parent directory exists
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Append to inbox
    with open(INBOX_PATH, "a", encoding="utf-8") as f:
        f.write(entry)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "arec-slack-listener"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=False)
