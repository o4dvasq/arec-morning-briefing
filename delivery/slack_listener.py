"""
Slack assistant listener — Claude-powered inline assistant for AREC.
Receives DMs, processes with full memory context, executes actions.
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import anthropic
import yaml

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from sources.memory_reader import load_all_memory
from slack_sdk import WebClient

load_dotenv()

app = Flask(__name__)

# Paths
INBOX_PATH = Path("~/Dropbox/Tech/ClaudeProductivity/inbox.md").expanduser()
TASKS_PATH = Path("~/Dropbox/Tech/ClaudeProductivity/TASKS.md").expanduser()
MEMORY_BASE = Path("~/Dropbox/Tech/ClaudeProductivity/memory").expanduser()
CONVERSATION_HISTORY_PATH = Path("~/.arec_briefing_conversation_history.json").expanduser()
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

# Slack client
slack_client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])

SYSTEM_PROMPT = """You are Oscar Vasquez's personal AI chief of staff, accessible via Slack.
Oscar is COO of Avila Real Estate Capital (AREC), a private credit real estate fund.
Hard close for Fund II is June 30, 2026, $1B AUM target.

You have full access to Oscar's memory files: tasks, projects, people, company context.
Use this context to answer questions accurately.

Rules:
- Be concise. This is Slack — not email. Max 3-4 short paragraphs.
- Use *bold* for names, amounts, dates (Slack markdown).
- If adding a task, confirm what you added and which category.
- If updating a memory file, confirm what you updated.
- If answering a question, answer directly from the memory context.
  If you don't have enough context, say so clearly.
- Never make up facts about deals, investors, or people.
- Maintain conversational continuity using the chat history provided.
- End action confirmations with: "✓ Done" on its own line.

When the user wants you to take an action (add task, update memory), include special markers in your response:
- For tasks: [ACTION:TASK|category|task text]
- For memory updates: [ACTION:MEMORY|filepath|note text]

These markers will be stripped before posting to Slack."""


def load_config():
    """Load config.yaml."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_conversation_history():
    """Load last 10 message pairs from history file."""
    if not CONVERSATION_HISTORY_PATH.exists():
        return []
    try:
        with open(CONVERSATION_HISTORY_PATH, 'r') as f:
            history = json.load(f)
            return history[-20:]  # Last 10 pairs = 20 messages
    except:
        return []


def save_conversation_history(history):
    """Save conversation history, keeping only last 10 pairs."""
    trimmed = history[-20:]  # Last 10 pairs = 20 messages
    CONVERSATION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONVERSATION_HISTORY_PATH, 'w') as f:
        json.dump(trimmed, f, indent=2)


def append_inbox(message: str, intent: str):
    """Log interaction to inbox.md."""
    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"- [SLACK ASSISTANT {intent} {today}]: {message}\n"
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INBOX_PATH, 'a', encoding='utf-8') as f:
        f.write(entry)


def append_task(task_text: str, category: str):
    """Append a new open task to TASKS.md under the correct category."""
    try:
        if not TASKS_PATH.exists():
            TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
            TASKS_PATH.write_text(f"## {category}\n\n", encoding='utf-8')

        content = TASKS_PATH.read_text(encoding='utf-8')
        lines = content.splitlines(keepends=True)

        # Find category heading
        target_heading = f"## {category}"
        fallback_heading = "## Work — Operations"
        insert_index = None

        for i, line in enumerate(lines):
            if line.strip() == target_heading:
                insert_index = i + 1
                break

        # If not found, try fallback
        if insert_index is None:
            for i, line in enumerate(lines):
                if line.strip() == fallback_heading:
                    insert_index = i + 1
                    break

        # If still not found, append to end
        if insert_index is None:
            lines.append(f"\n{fallback_heading}\n")
            insert_index = len(lines)

        # Insert task
        task_line = f"- [ ] {task_text}\n"
        lines.insert(insert_index, task_line)

        TASKS_PATH.write_text(''.join(lines), encoding='utf-8')
        return True
    except Exception as e:
        append_inbox(f"ERROR appending task: {e}", "ERROR")
        return False


def append_memory_note(filename: str, note: str):
    """Append timestamped note to a memory file."""
    try:
        file_path = MEMORY_BASE / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d")
        entry = f"\n## Note — {today}\n{note}\n"

        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(entry)
        return True
    except Exception as e:
        append_inbox(f"ERROR updating memory: {e}", "ERROR")
        return False


def format_tasks(tasks_dict):
    """Format tasks for context."""
    if not tasks_dict:
        return "No open tasks."
    lines = []
    for category, tasks in tasks_dict.items():
        if tasks:
            lines.append(f"\n{category}:")
            for task in tasks[:8]:  # Limit to 8 per category
                lines.append(f"  - {task}")
    return "\n".join(lines)


def format_people(people_dict):
    """Format people context."""
    if not people_dict:
        return "No people notes."
    lines = []
    for name, bio in list(people_dict.items())[:8]:  # Limit to 8
        lines.append(f"\n{name}:\n{bio[:250]}")
    return "\n".join(lines)


def process_message(user_message: str, memory_context: dict, history: list) -> tuple[str, str]:
    """
    Call Claude to process message with full context.
    Returns: (response_text, intent)
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # Build context prompt
    context = f"""=== CURRENT MEMORY CONTEXT ===

OPEN TASKS:
{format_tasks(memory_context['open_tasks'])}

INBOX ITEMS:
{chr(10).join(memory_context['inbox_items'][:10]) if memory_context['inbox_items'] else 'Empty'}

FUND II STATUS:
{memory_context['fund_ii'][:1200]}

COMPANY CONTEXT:
{memory_context['company'][:900]}

PEOPLE CONTEXT:
{format_people(memory_context['people'])}

=== USER MESSAGE ===
{user_message}"""

    # Build messages array with history
    messages = history.copy()
    messages.append({"role": "user", "content": context})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=SYSTEM_PROMPT,
        messages=messages
    )

    response_text = response.content[0].text

    # Detect intent from response
    intent = "FEEDBACK"
    lower_response = response_text.lower()

    if "[ACTION:TASK|" in response_text:
        intent = "TASK"
    elif "[ACTION:MEMORY|" in response_text:
        intent = "MEMORY_UPDATE"
    elif any(q in user_message.lower() for q in ["what", "who", "when", "where", "how", "tell me", "show me"]):
        intent = "QUERY"

    return response_text, intent


def parse_and_execute_actions(response_text: str) -> str:
    """
    Parse action markers from response and execute them.
    Returns cleaned response text without markers.
    """
    import re

    # Extract and execute TASK actions
    task_pattern = r'\[ACTION:TASK\|([^\|]+)\|([^\]]+)\]'
    for match in re.finditer(task_pattern, response_text):
        category = match.group(1).strip()
        task_text = match.group(2).strip()
        append_task(task_text, category)

    # Extract and execute MEMORY actions
    memory_pattern = r'\[ACTION:MEMORY\|([^\|]+)\|([^\]]+)\]'
    for match in re.finditer(memory_pattern, response_text):
        filepath = match.group(1).strip()
        note_text = match.group(2).strip()
        append_memory_note(filepath, note_text)

    # Remove all action markers
    clean_response = re.sub(task_pattern, '', response_text)
    clean_response = re.sub(memory_pattern, '', clean_response)

    return clean_response.strip()


@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.json

    # Handle Slack URL verification challenge
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data["challenge"]})

    # Handle incoming messages
    if data.get("type") == "event_callback":
        event = data.get("event", {})

        # Only process direct messages
        if event.get("type") == "message" and event.get("channel_type") == "im":
            # Ignore bot messages and message edits
            if event.get("subtype") is None and "bot_id" not in event:
                message_text = event.get("text", "").strip()
                channel = event.get("channel")

                if message_text:
                    try:
                        # Load memory context
                        config = load_config()
                        memory = load_all_memory(config)

                        # Load conversation history
                        history = load_conversation_history()

                        # Process with Claude
                        response_text, intent = process_message(
                            message_text, memory, history
                        )

                        # Execute any actions embedded in response
                        clean_response = parse_and_execute_actions(response_text)

                        # Always log to inbox
                        append_inbox(message_text, intent)

                        # Save conversation history
                        history.append({"role": "user", "content": message_text})
                        history.append({"role": "assistant", "content": clean_response})
                        save_conversation_history(history)

                        # Post response to Slack
                        slack_client.chat_postMessage(
                            channel=channel,
                            text=clean_response
                        )

                    except Exception as e:
                        error_msg = f"Error processing message: {str(e)}"
                        append_inbox(error_msg, "ERROR")
                        slack_client.chat_postMessage(
                            channel=channel,
                            text=f"Sorry, I encountered an error: {str(e)}"
                        )

    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "arec-slack-assistant"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=False)
