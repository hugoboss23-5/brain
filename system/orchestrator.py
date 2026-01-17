import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BRAIN = BASE
SYSTEM = BASE / 'system'

REGISTRY = SYSTEM / 'agents' / 'registry.json'
TO_CLAUDE = SYSTEM / 'queues' / 'to_claude_code'
FROM_CLAUDE = SYSTEM / 'queues' / 'from_claude_code'

def load_registry():
    # Windows PowerShell often writes UTF-8 with BOM. Use utf-8-sig to strip it.
    return json.loads(REGISTRY.read_text(encoding='utf-8-sig'))

def list_tasks():
    return list(TO_CLAUDE.glob('*.task'))

def main():
    _ = load_registry()
    tasks = list_tasks()

    if not tasks:
        print("No tasks for Claude Code.")
        return

    print(f"{len(tasks)} task(s) awaiting Claude Code.")
    for task in tasks:
        print(f"- {task.name}")

if __name__ == "__main__":
    main()
