import datetime as dt
from pathlib import Path
import subprocess, sys

BASE = Path(__file__).resolve().parent.parent
TO_CLAUDE = BASE / "system" / "queues" / "to_claude_code"

def main():
    tasks = sorted(TO_CLAUDE.glob("*.task"))
    if not tasks:
        print("No tasks to execute.")
        return
    # Prefer real Claude runner if API key present
    import os
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        code = subprocess.call([sys.executable, str(BASE / "system" / "runner_claude_code.py")])
        raise SystemExit(code)
    raise SystemExit("ANTHROPIC_API_KEY not set; refusing to run tasks without real Claude runner.")

if __name__ == "__main__":
    main()
