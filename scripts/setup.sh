#!/bin/bash
# One-time setup: install deps and register 5 AM launchd agent.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_SRC="$SCRIPT_DIR/com.arec.morningbriefing.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.arec.morningbriefing.plist"

echo "=== AREC Morning Briefing Setup ==="

echo "Installing Python dependencies..."
pip3 install -r "$PROJECT_DIR/requirements.txt"

echo "Installing launchd agent..."
sed "s|PROJECT_DIR_PLACEHOLDER|$PROJECT_DIR|g" "$PLIST_SRC" > "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo ""
echo "✓ Done. Briefing will run at 5:00 AM daily."
echo ""
echo "Next steps:"
echo "  1. cp .env.example .env && nano .env   (add your API keys)"
echo "  2. python3 auth/graph_auth.py --setup   (Microsoft auth)"
echo "  3. bash scripts/test_run.sh              (test it now)"
echo ""
echo "Logs: tail -f ~/Library/Logs/arec-morning-briefing.log"
