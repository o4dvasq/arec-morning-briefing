#!/bin/bash
# Run the briefing manually for testing.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
echo "Running AREC Morning Briefing (manual test)..."
python3 main.py
