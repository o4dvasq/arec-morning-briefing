#!/bin/bash
# Start the Slack feedback listener on port 3000
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "Starting AREC Slack Listener on port 3000..."
python3 delivery/slack_listener.py
