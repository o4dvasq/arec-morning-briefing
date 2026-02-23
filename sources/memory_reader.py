"""
Reads and parses Claude Productivity markdown files from Dropbox.
Extracts open tasks, project context, inbox items, and people notes.
"""

from pathlib import Path


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""

def _extract_open_tasks(tasks_md: str) -> dict[str, list[str]]:
    """Parse TASKS.md, return open tasks grouped by section. Stop at Done."""
    categories = {}
    current_category = "General"
    for line in tasks_md.splitlines():
        if line.startswith("## "):
            current_category = line.lstrip("# ").strip()
            if current_category.lower() == "done":
                break
            continue
        if line.strip().startswith("- [ ]"):
            task = line.strip()[6:].strip()
            task = task.replace("_(their action)_", "[THEIR ACTION]")
            task = task.replace("_(Tony action)_", "[TONY'S ACTION]")
            categories.setdefault(current_category, []).append(task)
    return categories

def _extract_inbox_items(inbox_md: str) -> list[str]:
    items = []
    for line in inbox_md.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            items.append(s)
    return items[:10]

def _load_people_files(people_dir: Path) -> dict[str, str]:
    people = {}
    if not people_dir.exists():
        return people
    for f in people_dir.glob("*.md"):
        name = f.stem.replace("-", " ").title()
        people[name] = _read(f)[:400]
    return people

def load_all_memory(config: dict) -> dict:
    """Load all memory files, return structured context dict."""
    base = Path(config["memory"]["base_path"]).expanduser()
    files = config["memory"]["files"]
    return {
        "open_tasks": _extract_open_tasks(_read(base / files["tasks"])),
        "inbox_items": _extract_inbox_items(_read(base / files["inbox"])),
        "fund_ii": _read(base / files["fund_ii"])[:2000],
        "company": _read(base / files["company"])[:1500],
        "claude_context": _read(base / files["claude_context"])[:1000],
        "people": _load_people_files(base / config["memory"]["people_dir"]),
    }
