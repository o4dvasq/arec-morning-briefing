"""
AREC Morning Briefing — orchestrator.
Flow: load memory → fetch Graph data → generate with Claude → post to Slack.
"""

import os
import sys
import logging
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

log_path = Path("~/Library/Logs/arec-morning-briefing.log").expanduser()
log_path.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    log.info("=== AREC Morning Briefing starting ===")
    try:
        config = load_config()
        log.info("Config loaded.")

        from sources.memory_reader import load_all_memory
        memory = load_all_memory(config)
        task_count = sum(len(v) for v in memory["open_tasks"].values())
        log.info(f"Memory loaded: {task_count} tasks, {len(memory['people'])} people.")

        from sources.ms_graph import get_todays_events, get_recent_emails
        events = get_todays_events(config["briefing"]["calendar_days_ahead"])
        log.info(f"Calendar: {len(events)} events.")

        emails = get_recent_emails(
            hours_back=config["briefing"]["email_scan_hours"],
            max_results=config["briefing"]["email_max_results"],
        )
        log.info(f"Email: {len(emails)} messages.")

        from briefing.generator import generate_briefing
        briefing_text = generate_briefing(events, emails, memory, config)
        log.info(f"Briefing generated ({len(briefing_text)} chars).")

        from delivery.slack_sender import post_briefing
        post_briefing(briefing_text)
        log.info("✓ Briefing delivered to Slack.")

    except Exception as e:
        log.error(f"Briefing failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
